from __future__ import annotations

import logging
from importlib import import_module
from importlib.metadata import EntryPoints, entry_points
from importlib.resources import as_file, files
from typing import Any, Literal, TypedDict, TypeVar, Union

import yaml
from sunflare.device import Device
from sunflare.presenter import Presenter
from sunflare.view import View

logger = logging.getLogger("redsun")

T = TypeVar("T")

# Type aliases
ManifestItems = dict[str, dict[str, str]]
PluginType = Union[type[Device], type[Presenter], type[View]]
PLUGIN_GROUPS = Literal["models", "controllers", "views"]


class PluginTypeDict(TypedDict):
    """Typed dictionary for discovered plugin classes, organized by group.

    Attributes
    ----------
    models : dict[str, type[PDevice]]
        Dictionary of device classes.
    controllers : dict[str, type[PPresenter]]
        Dictionary of presenter classes.
    views : dict[str, type[PView]]
        Dictionary of view classes.
    """

    models: dict[str, type[Device]]
    controllers: dict[str, type[Presenter]]
    views: dict[str, type[View]]


def load_configuration(
    config_path: str,
) -> tuple[dict[str, Any], PluginTypeDict]:
    """Load configuration and discover plugin classes from a YAML file.

    Reads the YAML configuration, discovers installed plugins via
    entry points, imports and validates their classes against sunflare
    protocols.

    Parameters
    ----------
    config_path : str
        Path to the YAML configuration file.

    Returns
    -------
    tuple[dict[str, Any], PluginTypeDict]
        The raw configuration dictionary and the discovered plugin classes.
        The config dict preserves the full YAML structure including
        ``session``, ``frontend``, and per-component kwargs.
    """
    with open(config_path, "r") as f:
        config: dict[str, Any] = yaml.safe_load(f)

    plugin_types = PluginTypeDict(models={}, controllers={}, views={})
    available_manifests = entry_points(group="redsun.plugins")

    groups: list[PLUGIN_GROUPS] = ["models", "controllers", "views"]

    for group in groups:
        if group not in config:
            logger.debug(
                "Group %s not found in the configuration file. Skipping", group
            )
            continue
        loaded = _load_plugins(
            group_cfg=config[group],
            group=group,
            available_manifests=available_manifests,
        )
        for name, cls in loaded:
            # this assignment is safe at runtime;
            # for mypy sake we should have a better
            # way of dealing with the different plugin types
            # in order to remove the type: ignore comment
            plugin_types[group][name] = cls  # type: ignore

    return config, plugin_types


def _load_plugins(
    *,
    group_cfg: dict[str, Any],
    group: str,
    available_manifests: EntryPoints,
) -> list[tuple[str, PluginType]]:
    """Load plugin classes for a given group.

    For each entry in the group configuration, find the matching entry
    point, read the plugin manifest, import the class, and validate it.

    Parameters
    ----------
    group_cfg : dict[str, Any]
        Configuration entries for the group from the YAML file.
    group : str
        The plugin group (``"models"``, ``"controllers"``, or ``"views"``).
    available_manifests : EntryPoints
        The available ``redsun.plugins`` entry points.

    Returns
    -------
    list[tuple[str, PluginType]]
        A list of ``(name, class)`` tuples for successfully loaded plugins.
    """
    plugins: list[tuple[str, PluginType]] = []

    for name, info in group_cfg.items():
        plugin_name: str = info["plugin_name"]
        plugin_id: str = info["plugin_id"]

        iterator = (entry for entry in available_manifests if entry.name == plugin_name)
        plugin = next(iterator, None)

        if plugin is None:
            logger.error('Plugin "%s" not found in the installed plugins.', plugin_name)
            continue

        pkg_manifest = files(plugin.name.replace("-", "_")) / plugin.value
        with as_file(pkg_manifest) as manifest_path:
            with open(manifest_path, "r") as f:
                manifest: dict[str, ManifestItems] = yaml.safe_load(f)

            if group not in manifest:
                logger.error(
                    'Plugin "%s" manifest does not contain group "%s".',
                    plugin_name,
                    group,
                )
                continue

            items = manifest[group]
            if plugin_id not in items:
                logger.error(
                    'Plugin "%s" does not contain the id "%s".',
                    plugin_name,
                    plugin_id,
                )
                continue

            item = items[plugin_id]
            try:
                class_item_module, class_item_type = item["class"].split(":")
                imported_class = getattr(
                    import_module(class_item_module), class_item_type
                )
            except KeyError:
                logger.error(
                    'Plugin id "%s" of "%s" does not contain the class key. Skipping.',
                    plugin_id,
                    name,
                )
                continue

            if not _check_import(imported_class, group):
                logger.error(
                    "%s exists, but does not implement any known protocol.",
                    imported_class,
                )
                continue

            plugins.append((name, imported_class))

    return plugins


def _check_import(imported_class: type[T], group: str) -> bool:
    """Check if the imported class implements the correct protocol.

    Parameters
    ----------
    imported_class : type
        The imported class to check.
    group : str
        The group to check the class against.

    Returns
    -------
    bool
        ``True`` if the class implements the correct protocol.
    """
    if group == "models":
        return _check_device_protocol(imported_class)
    elif group == "controllers":
        return _check_presenter_protocol(imported_class)
    elif group == "views":
        return _check_view_protocol(imported_class)
    else:
        raise ValueError(f"Unknown group {group}.")  # pragma: no cover


def _check_device_protocol(cls: type) -> bool:
    """Check if a class implements the device protocol.

    Devices should inherit from :class:`~sunflare.device.Device` or
    structurally implement :class:`~sunflare.device.PDevice`.
    """
    # Check inheritance hierarchy
    if Device in cls.mro():
        return True

    # Structural check: required methods and properties
    required_methods = ["read_configuration", "describe_configuration"]
    required_properties = ["name", "parent"]

    for method_name in required_methods:
        if not hasattr(cls, method_name) or not callable(getattr(cls, method_name)):
            return False

    for prop_name in required_properties:
        if not hasattr(cls, prop_name):
            return False

    return True


def _check_presenter_protocol(cls: type) -> bool:
    """Check if a class implements the presenter protocol.

    Presenters should inherit from :class:`~sunflare.presenter.Presenter`
    or structurally implement :class:`~sunflare.presenter.PPresenter`.
    """
    # Check inheritance hierarchy
    if Presenter in cls.mro():
        return True

    # Structural check: required attributes
    required_attributes = ["devices", "virtual_bus"]
    return all(hasattr(cls, attr) for attr in required_attributes)


def _check_view_protocol(cls: type) -> bool:
    """Check if a class implements the view protocol.

    Views should inherit from :class:`~sunflare.view.View` or
    structurally implement :class:`~sunflare.view.PView`.
    """
    if issubclass(cls, View):
        return True

    # Structural check: virtual_bus must be present
    return hasattr(cls, "virtual_bus")
