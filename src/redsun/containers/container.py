"""Application container for MVP architecture.

Provides `AppContainer` for declarative component registration
and dependency-ordered instantiation.
"""

from __future__ import annotations

import asyncio
import logging
from enum import Enum, unique
from importlib import import_module
from importlib.metadata import EntryPoints, entry_points
from importlib.resources import as_file, files
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Literal,
    TypedDict,
    TypeGuard,
    TypeVar,
    assert_never,
    overload,
)

import yaml
from ophyd_async.core import Device

from redsun.aio import _loop_factory, run_coro
from redsun.containers._config import AppConfig
from redsun.containers.components import (
    _DeviceComponent,
    _DeviceField,
    _PresenterComponent,
    _PresenterField,
    _ViewComponent,
    _ViewField,
    expects_positionals,
)
from redsun.presenter import PPresenter
from redsun.view import PView
from redsun.virtual import (
    Connection,
    HasShutdown,
    IsInjectable,
    IsProvider,
    VirtualContainer,
    WiringError,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Self, TypeAlias

    from psygnal import SignalInstance

    from redsun.containers.components import _ComponentBase
    from redsun.virtual import RedSunConfig
    from redsun.virtual._wiring import SlotThread

    _ComponentFactory: TypeAlias = Callable[..., _ComponentBase[Any]]

ManifestItems = dict[str, Any]
PluginType = type[Device] | type[PPresenter] | type[PView]
PLUGIN_GROUPS = Literal["devices", "presenters", "views"]

_AnyField = _DeviceField | _PresenterField | _ViewField


@unique
class Frontend(str, Enum):
    """Supported frontend types."""

    PYQT = "pyqt"
    PYSIDE = "pyside"


class _PluginTypeDict(TypedDict):
    """Typed dictionary for discovered plugin classes, organized by group."""

    devices: dict[str, type[Device]]
    presenters: dict[str, type[PPresenter]]
    views: dict[str, type[PView]]


def _check_device_protocol(cls: type) -> TypeGuard[type[Device]]:
    """Check if a class is an ophyd-async Device subclass."""
    try:
        return issubclass(cls, Device)
    except TypeError:
        return False


def _check_presenter_protocol(cls: type) -> TypeGuard[type[PPresenter]]:
    """Class-level gate of the dual presenter validation.

    The constructor must accept exactly ``(name, devices)`` as its leading
    positional parameters - the only part of the contract knowable before
    instantiation (keyword arguments are uncontrolled; instance attributes
    are invisible). PPresenter compliance is then validated on the built
    instance by ``_PresenterComponent.build``.
    """
    return isinstance(cls, type) and expects_positionals(cls, ("name", "devices"))


def _check_view_protocol(cls: type) -> TypeGuard[type[PView]]:
    """Class-level gate of the dual view validation.

    The constructor must accept exactly ``(name,)`` as its leading
    positional parameter - the only part of the contract knowable before
    instantiation. PView compliance is then validated on the built
    instance by ``_ViewComponent.build``.
    """
    return isinstance(cls, type) and expects_positionals(cls, ("name",))


@overload
def _check_plugin_protocol(
    imported_class: type, group: Literal["devices"]
) -> TypeGuard[type[Device]]: ...
@overload
def _check_plugin_protocol(
    imported_class: type, group: Literal["presenters"]
) -> TypeGuard[type[PPresenter]]: ...
@overload
def _check_plugin_protocol(
    imported_class: type, group: Literal["views"]
) -> TypeGuard[type[PView]]: ...
def _check_plugin_protocol(imported_class: type, group: PLUGIN_GROUPS) -> bool:
    match group:
        case "devices":
            return _check_device_protocol(imported_class)
        case "presenters":
            return _check_presenter_protocol(imported_class)
        case "views":
            return _check_view_protocol(imported_class)
        case _:
            assert_never(group)


T = TypeVar("T")

logger = logging.getLogger("redsun")

_PLUGIN_META_KEYS: frozenset[str] = frozenset({"plugin_name", "plugin_id"})

_PLUGIN_EXPECTATIONS: dict[PLUGIN_GROUPS, str] = {
    "devices": "must subclass ophyd_async.core.Device",
    "presenters": (
        "must accept exactly ('name', 'devices') as its leading positional parameters"
    ),
    "views": "must accept exactly ('name',) as its leading positional parameter",
}

_FRONTEND_CONTAINERS: dict[str, str] = {
    "pyqt": "redsun.containers.qt._container.QtAppContainer",
    "pyside": "redsun.containers.qt._container.QtAppContainer",
}


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file and validate required keys against AppConfig."""
    with open(path) as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise TypeError(
            f"Expected a YAML mapping at top level in {path}, got {type(data).__name__}"
        )
    required_keys = AppConfig.__required_keys__
    missing = required_keys - data.keys()
    if missing:
        raise KeyError(
            f"Configuration file {path} is missing required keys: "
            f"{', '.join(sorted(missing))}"
        )
    return data


def _resolve_frontend_container(frontend: str) -> type[AppContainer]:
    """Resolve a frontend string to the appropriate container class."""
    dotted_path = _FRONTEND_CONTAINERS.get(frontend)
    if dotted_path is None:
        raise ValueError(
            f"Unknown frontend {frontend!r}. Supported: {sorted(_FRONTEND_CONTAINERS)}"
        )
    module_path, class_name = dotted_path.rsplit(".", 1)
    module = import_module(module_path)
    ret_cls: type[AppContainer] = getattr(module, class_name)
    return ret_cls


class AppContainer:
    """Application container for MVP architecture."""

    __slots__ = (
        "_built_devices",
        "_config",
        "_devices_connected",
        "_is_built",
        "_virtual_container",
    )

    _device_components: ClassVar[dict[str, _DeviceComponent]] = {}
    _presenter_components: ClassVar[dict[str, _PresenterComponent]] = {}
    _view_components: ClassVar[dict[str, _ViewComponent]] = {}
    _config_path: ClassVar[Path | None] = None

    def __init_subclass__(
        cls,
        config: str | Path | None = None,
        **kwargs: Any,
    ) -> None:
        """Collect component wrappers from class attributes.

        Parameters
        ----------
        config : str | Path | None
            Path to a YAML configuration file for component kwargs.
        """
        super().__init_subclass__(**kwargs)

        if config is not None:
            cls._config_path = Path(config)

        devices: dict[str, _DeviceComponent] = {}
        presenters: dict[str, _PresenterComponent] = {}
        views: dict[str, _ViewComponent] = {}

        for base in cls.__bases__:
            if issubclass(base, AppContainer):
                devices.update(base._device_components)
                presenters.update(base._presenter_components)
                views.update(base._view_components)

        namespace = vars(cls)

        for attr_name, attr_value in namespace.items():
            if attr_name.startswith("_"):
                continue

            if isinstance(attr_value, _DeviceComponent):
                devices[attr_value.name] = attr_value
            elif isinstance(attr_value, _PresenterComponent):
                presenters[attr_value.name] = attr_value
            elif isinstance(attr_value, _ViewComponent):
                views[attr_value.name] = attr_value

        component_fields = {
            attr_name: value
            for attr_name, value in namespace.items()
            if not attr_name.startswith("_") and isinstance(value, _AnyField)
        }

        if component_fields:
            config_data: dict[str, Any] = {}
            if cls._config_path is not None:
                config_data = _load_yaml(cls._config_path)

            _section_key: dict[type, str] = {
                _DeviceField: "devices",
                _PresenterField: "presenters",
                _ViewField: "views",
            }

            for attr_name, field in component_fields.items():
                kw = field.kwargs
                if field.from_config is not None:
                    if not config_data:
                        raise TypeError(
                            f"Component field '{attr_name}' in {cls.__name__} has "
                            f"from_config set but no config path was "
                            f"provided to the container class"
                        )

                    section_key = _section_key[type(field)]
                    section_data: dict[str, Any] = config_data.get(section_key, {})
                    _sentinel = object()
                    cfg_section = section_data.get(field.from_config, _sentinel)

                    if cfg_section is _sentinel:
                        logger.warning(
                            f"No config section '{field.from_config}' found in "
                            f"'{section_key}' for component field '{attr_name}' in {cls.__name__}, "
                            f"using inline kwargs only"
                        )
                        kw = field.kwargs
                    else:
                        kw = {**(cfg_section or {}), **field.kwargs}

                comp_name = field.alias if field.alias is not None else attr_name

                wrapper: _DeviceComponent | _PresenterComponent | _ViewComponent
                if isinstance(field, _DeviceField):
                    wrapper = _DeviceComponent(field.cls, comp_name, **kw)
                    devices[comp_name] = wrapper
                elif isinstance(field, _PresenterField):
                    wrapper = _PresenterComponent(field.cls, comp_name, **kw)
                    presenters[comp_name] = wrapper
                else:
                    wrapper = _ViewComponent(field.cls, comp_name, **kw)
                    views[comp_name] = wrapper
                setattr(cls, attr_name, wrapper)

        cls._device_components = devices
        cls._presenter_components = presenters
        cls._view_components = views

        if devices or presenters or views:
            logger.debug(
                f"Collected from {cls.__name__}: "
                f"{len(devices)} devices, "
                f"{len(presenters)} presenters, "
                f"{len(views)} views"
            )

    def __init__(self, *, session: str = "Redsun", frontend: str = "pyqt") -> None:
        self._config: AppConfig = {
            "schema_version": 1.0,
            "session": session,
            "frontend": frontend,
        }
        self._virtual_container: VirtualContainer | None = None
        self._is_built: bool = False
        self._built_devices: dict[str, Device] = {}
        self._devices_connected: bool = False

        # In the declarative subclass path (class MyApp(QtAppContainer, config=...))
        # the metaclass loads the YAML only to resolve component kwargs and never
        # populates _config with top-level sections such as 'storage', 'session',
        # or 'schema_version'.  We read those here so that build() sees the same
        # state as the from_config() path, which sets them explicitly.
        config_path: Path | None = getattr(type(self), "_config_path", None)
        if config_path is not None:
            try:
                yaml_data = _load_yaml(config_path)
            except Exception as e:  # noqa: BLE001 - unreadable config falls back to defaults
                logger.warning(f"Could not read config file {config_path}: {e}")
                yaml_data = {}
            _COMPONENT_SECTIONS = frozenset({"devices", "presenters", "views"})
            for key, value in yaml_data.items():
                if key not in _COMPONENT_SECTIONS:
                    self._config[key] = value  # type: ignore[literal-required]

    @property
    def config(self) -> AppConfig:
        """Return the application configuration."""
        return self._config

    @property
    def devices(self) -> dict[str, Device]:
        """Return built device instances."""
        if not self._is_built:
            raise RuntimeError("Container not built. Call build() first.")
        return {name: comp.instance for name, comp in self._device_components.items()}

    @property
    def presenters(self) -> dict[str, PPresenter]:
        """Return built presenter instances."""
        if not self._is_built:
            raise RuntimeError("Container not built. Call build() first.")
        return {
            name: comp.instance for name, comp in self._presenter_components.items()
        }

    @property
    def views(self) -> dict[str, PView]:
        """Return built view instances."""
        if not self._is_built:
            raise RuntimeError("Container not built. Call build() first.")
        return {name: comp.instance for name, comp in self._view_components.items()}

    @property
    def virtual_container(self) -> VirtualContainer:
        """Return the virtual container instance."""
        if self._virtual_container is None:
            raise RuntimeError("Container not built. Call build() first.")
        return self._virtual_container

    @property
    def is_built(self) -> bool:
        """Return whether the container has been built."""
        return self._is_built

    def wire(self) -> None:
        """Connect the signals and slots of built components.

        Override in a container subclass to declare the connections of an
        application. Every component is built by the time this runs and is
        reachable as the attribute it was declared under:

        ```python
        class MyApp(AppContainer):
            det_ctrl = declare_presenter(DetectorPresenter)
            img_widget = declare_view(ImageView)

            def wire(self) -> None:
                self.connect(self.det_ctrl.sig_new_data, self.img_widget.update_layers)
        ```

        The default implementation connects nothing.
        """

    def connect(
        self,
        signal: SignalInstance,
        slot: Callable[..., Any],
        *,
        thread: SlotThread = None,
    ) -> Connection:
        """Connect a signal to a slot, recording the link for teardown.

        See [`VirtualContainer.connect`][redsun.virtual.VirtualContainer.connect].
        """
        return self.virtual_container.connect(signal, slot, thread=thread)

    def _apply_wiring_config(self) -> None:
        """Connect the port pairs listed in the ``wiring`` configuration section."""
        for index, rule in enumerate(self._config.get("wiring", [])):
            if not isinstance(rule, dict) or rule.keys() != {"from", "to"}:
                raise WiringError(
                    f"wiring entry {index} must be a mapping with exactly the "
                    f"keys 'from' and 'to', got {rule!r}"
                )
            self.virtual_container.connect_paths(rule["from"], rule["to"])

    def build(self) -> Self:
        """Instantiate all components in dependency order.

        Build order:

        1. VirtualContainer
        2. Devices
        3. Presenters (register their providers in the VirtualContainer)
        4. Views (inject dependencies from the VirtualContainer)
        5. Wiring, connecting the signals and slots of built components
        6. Remaining dependency injection
        """
        if self._is_built:
            logger.warning("Container already built, skipping rebuild")
            return self

        # ensure the background loop
        # is running
        _ = _loop_factory()

        logger.info("Building application container...")

        self._virtual_container = VirtualContainer()

        base_cfg: RedSunConfig = {
            "schema_version": self._config.get("schema_version", 1.0),
            "session": self._config.get("session", "Redsun"),
            "frontend": self._config.get("frontend", "pyqt"),
        }
        self._virtual_container._set_configuration(base_cfg)
        logger.debug("VirtualContainer created")

        built_devices: dict[str, Device] = {}
        for name, device_comp in self._device_components.items():
            try:
                built_devices[name] = device_comp.build()
                logger.debug(f"Device '{name}' built")
            except Exception as e:  # noqa: BLE001 - a missing device must not abort the app
                logger.error(f"Failed to build device '{name}': {e}")

        for comp_name, presenter_component in self._presenter_components.items():
            try:
                presenter_component.build(built_devices)
            except Exception as e:
                logger.error(f"Failed to build presenter '{comp_name}': {e}")
                raise

        for comp_name, view_component in self._view_components.items():
            try:
                view_component.build()
            except Exception as e:
                logger.error(f"Failed to build view '{comp_name}': {e}")
                raise

        all_components: dict[str, _PresenterComponent | _ViewComponent] = {
            **self._presenter_components,
            **self._view_components,
        }
        for comp_name, component in all_components.items():
            if isinstance(component.instance, IsProvider):
                component.instance.register_providers(self._virtual_container)

        self._virtual_container._set_components(
            {name: comp.instance for name, comp in all_components.items()}
        )
        self.wire()
        self._apply_wiring_config()

        for comp_name, component in all_components.items():
            if isinstance(component.instance, IsInjectable):
                component.instance.inject_dependencies(self._virtual_container)

        self._built_devices = built_devices
        self._is_built = True
        logger.info(
            f"Container built: "
            f"{len(self._device_components)} devices, "
            f"{len(self._presenter_components)} presenters, "
            f"{len(self._view_components)} views"
        )

        return self

    def connect_devices(self, mock: bool = False) -> None:
        """Connect all devices via ophyd-async's async connect lifecycle.

        Call after [`build`][redsun.containers.container.AppContainer.build].
        Use ``mock=True`` in tests to skip hardware communication.

        Parameters
        ----------
        mock : bool
            If ``True``, connect using mock backends (no hardware required).

        Raises
        ------
        RuntimeError
            If called before [`build`][redsun.containers.container.AppContainer.build].
        """
        if not self._is_built:
            raise RuntimeError("Call build() before connect_devices()")

        async def _connect_all(mock: bool) -> None:
            await asyncio.gather(
                *[device.connect(mock=mock) for device in self._built_devices.values()]
            )

        run_coro(_connect_all(mock))
        self._devices_connected = True

    def shutdown(self) -> None:
        """Shutdown all presenters that implement ``HasShutdown``."""
        if not self._is_built:
            return

        if self._virtual_container is not None:
            self._virtual_container.disconnect_all()

        for name, comp in self._presenter_components.items():
            if isinstance(comp.instance, HasShutdown):
                try:
                    comp.instance.shutdown()
                except Exception as e:  # noqa: BLE001 - one failed shutdown must not block the rest
                    logger.error(f"Error shutting down presenter '{name}': {e}")

        self._is_built = False
        logger.info("Container shutdown complete")

    def run(self) -> None:
        """Build and connect devices if needed, then start the application."""
        if not self._is_built:
            self.build()
        if not self._devices_connected:
            self.connect_devices()

        frontend = self._config.get("frontend", "pyqt")
        logger.info(f"Starting application with frontend: {frontend}")

    @classmethod
    def from_config(cls, config_path: str) -> AppContainer:
        """Build a container dynamically from a YAML configuration file."""
        config, plugin_types = cls._load_configuration(config_path)

        namespace: dict[str, Any] = {}

        declared: tuple[tuple[PLUGIN_GROUPS, _ComponentFactory], ...] = (
            ("devices", _DeviceComponent),
            ("presenters", _PresenterComponent),
            ("views", _ViewComponent),
        )
        for group, component in declared:
            section: dict[str, Any] = config.get(group, {})
            for name, plugin_class in plugin_types[group].items():
                cfg_kwargs = {
                    k: v
                    for k, v in section.get(name, {}).items()
                    if k not in _PLUGIN_META_KEYS
                }
                namespace[name] = component(plugin_class, name, **cfg_kwargs)

        frontend = config.get("frontend", "pyqt")
        base_class = _resolve_frontend_container(frontend)

        DynamicApp: type[AppContainer] = type("DynamicApp", (base_class,), namespace)

        instance = DynamicApp(
            session=config.get("session", "Redsun"),
            frontend=frontend,
        )
        if "wiring" in config:
            instance._config["wiring"] = config["wiring"]

        return instance

    @classmethod
    def _load_configuration(
        cls, config_path: str
    ) -> tuple[dict[str, Any], _PluginTypeDict]:
        """Load configuration and discover plugin classes from a YAML file."""
        with open(config_path, "r") as f:
            config: dict[str, Any] = yaml.safe_load(f)

        plugin_types: _PluginTypeDict = {"devices": {}, "presenters": {}, "views": {}}
        available_manifests = entry_points(group="redsun.plugins")

        groups: list[PLUGIN_GROUPS] = ["devices", "presenters", "views"]

        for group in groups:
            if group not in config:
                logger.debug(
                    "Group %s not found in the configuration file. Skipping", group
                )
                continue
            loaded = cls._load_plugins(
                group_cfg=config[group],
                group=group,
                available_manifests=available_manifests,
            )
            for name, plugin_cls in loaded:
                plugin_types[group][name] = plugin_cls  # type: ignore[assignment]

        return config, plugin_types

    @classmethod
    def _load_plugins(
        cls,
        *,
        group_cfg: dict[str, Any],
        group: PLUGIN_GROUPS,
        available_manifests: EntryPoints,
    ) -> list[tuple[str, PluginType]]:
        """Load plugin classes for a given group from manifests."""
        plugins: list[tuple[str, PluginType]] = []

        for name, info in group_cfg.items():
            plugin_name: str = info["plugin_name"]
            plugin_id: str = info["plugin_id"]

            iterator = (
                entry for entry in available_manifests if entry.name == plugin_name
            )
            plugin = next(iterator, None)

            if plugin is None:
                logger.error(
                    'Plugin "%s" not found in the installed plugins.', plugin_name
                )
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

                class_path = items[plugin_id]
                try:
                    class_item_module, class_item_type = class_path.split(":")
                    imported_class = getattr(
                        import_module(class_item_module), class_item_type
                    )
                except (KeyError, ValueError):
                    logger.error(
                        'Plugin id "%s" of "%s" has invalid class path "%s". Skipping.',
                        plugin_id,
                        name,
                        class_path,
                    )
                    continue

                if not _check_plugin_protocol(imported_class, group):
                    logger.error(
                        "%s cannot be loaded as a plugin in group %r: it %s.",
                        imported_class,
                        group,
                        _PLUGIN_EXPECTATIONS[group],
                    )
                    continue

                plugins.append((name, imported_class))

        return plugins


__all__ = ["AppContainer", "Frontend"]
