"""Loading a session file's components from the plugins it names."""

from __future__ import annotations

import logging
from importlib import import_module
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    TypedDict,
    TypeGuard,
    assert_never,
    overload,
)

from ophyd_async.core import Device

from redsun.containers.components import expects_positionals
from redsun.presenter import PPresenter
from redsun.view import PView

from ._config import TRANSPORT_KEY, ConfigurationError, load_yaml
from ._manifest import ServiceEntry, discover

if TYPE_CHECKING:
    from ._manifest import PluginManifest

logger = logging.getLogger("redsun")

PluginType = type[Device] | type[PPresenter] | type[PView]
PLUGIN_GROUPS = Literal["devices", "presenters", "views"]

PLUGIN_META_KEYS: frozenset[str] = frozenset({"plugin_name", "plugin_id"})

PLUGIN_EXPECTATIONS: dict[PLUGIN_GROUPS, str] = {
    "devices": "must subclass ophyd_async.core.Device",
    "presenters": (
        "must accept exactly ('name', 'devices') as its leading positional parameters"
    ),
    "views": "must accept exactly ('name',) as its leading positional parameter",
}


class PluginTypes(TypedDict):
    """Discovered plugin classes, by group."""

    devices: dict[str, type[Device]]
    presenters: dict[str, type[PPresenter]]
    views: dict[str, type[PView]]


def check_device_protocol(cls: type) -> TypeGuard[type[Device]]:
    """Return whether a class subclasses the ``ophyd-async`` Device."""
    try:
        return issubclass(cls, Device)
    except TypeError:
        return False


def check_presenter_protocol(cls: type) -> TypeGuard[type[PPresenter]]:
    """Check a presenter class before it is built.

    The constructor's leading positional parameters must be exactly
    ``(name, devices)``, the only part of the contract knowable before
    instantiation. ``_PresenterComponent.build`` checks PPresenter on the
    instance.
    """
    return isinstance(cls, type) and expects_positionals(cls, ("name", "devices"))


def check_view_protocol(cls: type) -> TypeGuard[type[PView]]:
    """Check a view class before it is built.

    The constructor's leading positional parameter must be exactly ``(name,)``,
    the only part of the contract knowable before instantiation.
    ``_ViewComponent.build`` checks PView on the instance.
    """
    return isinstance(cls, type) and expects_positionals(cls, ("name",))


@overload
def check_plugin_protocol(
    imported_class: type, group: Literal["devices"]
) -> TypeGuard[type[Device]]: ...
@overload
def check_plugin_protocol(
    imported_class: type, group: Literal["presenters"]
) -> TypeGuard[type[PPresenter]]: ...
@overload
def check_plugin_protocol(
    imported_class: type, group: Literal["views"]
) -> TypeGuard[type[PView]]: ...
def check_plugin_protocol(imported_class: type, group: PLUGIN_GROUPS) -> bool:
    match group:
        case "devices":
            return check_device_protocol(imported_class)
        case "presenters":
            return check_presenter_protocol(imported_class)
        case "views":
            return check_view_protocol(imported_class)
        case _:
            assert_never(group)


def load_configuration(
    config_path: str,
) -> tuple[dict[str, Any], PluginTypes, dict[str, dict[str, Any]]]:
    """Load configuration, discover plugin classes and resolve services.

    Services are returned as each declaration's keyword arguments. A
    service naming a plugin takes its module and readiness line from the
    plugin's manifest, overridden by the session file.

    Raises
    ------
    ConfigurationError
        If the file does not validate, or names a device, presenter or view
        without the plugin it comes from.
    """
    paths = [Path(config_path)]
    config = load_yaml(paths)
    unnamed = [
        f"{group}.{name}: names no plugin; a component in a file built with "
        "from_config takes plugin_name and plugin_id"
        for group in ("devices", "presenters", "views")
        for name, entry in (config.get(group) or {}).items()
        if not {"plugin_name", "plugin_id"} <= entry.keys()
    ]
    if unnamed:
        raise ConfigurationError(paths, unnamed)

    plugin_types: PluginTypes = {"devices": {}, "presenters": {}, "views": {}}
    available_manifests = discover()

    services = services_of(config, available_manifests)

    groups: list[PLUGIN_GROUPS] = ["devices", "presenters", "views"]

    for group in groups:
        # a section written with nothing under it parses as None
        if not config.get(group):
            logger.debug(
                "Group %s not found in the configuration file. Skipping", group
            )
            continue
        loaded = load_plugins(
            group_cfg=config[group],
            group=group,
            available_manifests=available_manifests,
        )
        for name, plugin_cls in loaded:
            plugin_types[group][name] = plugin_cls  # type: ignore[assignment]

    return config, plugin_types, services


def services_of(
    config: dict[str, Any], manifests: dict[str, PluginManifest]
) -> dict[str, dict[str, Any]]:
    """Return the keyword arguments of every service a session file declares.

    A service naming a plugin takes its module and readiness line from that
    plugin's manifest, overridden by what the session file writes.
    """
    services: dict[str, dict[str, Any]] = {}
    section: dict[str, Any] = dict(config.get("services") or {})
    section.pop(TRANSPORT_KEY, None)
    for name, entry in section.items():
        kwargs = {k: v for k, v in entry.items() if k not in PLUGIN_META_KEYS}
        if "plugin_name" in entry:
            launched = manifest_item(
                entry["plugin_name"], "services", entry["plugin_id"], manifests
            )
            if not isinstance(launched, ServiceEntry):
                # manifest_item already logged why it returned None
                continue
            kwargs = {**launched.model_dump(exclude_unset=True), **kwargs}
        services[name] = kwargs
    return services


def manifest_item(
    plugin_name: str,
    group: PLUGIN_GROUPS | Literal["services"],
    plugin_id: str,
    available_manifests: dict[str, PluginManifest],
) -> str | ServiceEntry | None:
    """Return what *plugin_name*'s manifest lists as *plugin_id* under *group*.

    ``None``, with the reason logged, if the plugin is not installed, its
    manifest was left out as invalid, or it lacks the entry.
    """
    manifest = available_manifests.get(plugin_name)
    if manifest is None:
        logger.error(
            'Plugin "%s" is not installed, or its manifest was left out as invalid.',
            plugin_name,
        )
        return None

    items: dict[str, str] | dict[str, ServiceEntry] = getattr(manifest, group)
    if plugin_id not in items:
        logger.error(
            'Plugin "%s" does not contain the id "%s".', plugin_name, plugin_id
        )
        return None
    return items[plugin_id]


def load_plugins(
    *,
    group_cfg: dict[str, Any],
    group: PLUGIN_GROUPS,
    available_manifests: dict[str, PluginManifest],
) -> list[tuple[str, PluginType]]:
    """Load a group's plugin classes from their manifests."""
    plugins: list[tuple[str, PluginType]] = []

    for name, info in group_cfg.items():
        plugin_id: str = info["plugin_id"]
        class_path = manifest_item(
            info["plugin_name"], group, plugin_id, available_manifests
        )
        if not isinstance(class_path, str):
            continue
        try:
            class_item_module, class_item_type = class_path.split(":")
            imported_class = getattr(import_module(class_item_module), class_item_type)
        except (KeyError, ValueError):
            logger.error(
                'Plugin id "%s" of "%s" has invalid class path "%s". Skipping.',
                plugin_id,
                name,
                class_path,
            )
            continue

        if not check_plugin_protocol(imported_class, group):
            logger.error(
                "%s cannot be loaded as a plugin in group %r: it %s.",
                imported_class,
                group,
                PLUGIN_EXPECTATIONS[group],
            )
            continue

        plugins.append((name, imported_class))

    return plugins
