"""Application container for MVP architecture.

Provides `AppContainer` and its metaclass `AppContainerMeta`
for declarative component registration and dependency-ordered instantiation.
"""

from __future__ import annotations

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
    Protocol,
    TypedDict,
    TypeGuard,
    TypeVar,
    Union,
    overload,
    runtime_checkable,
)
from typing import _ProtocolMeta  # type: ignore[attr-defined]

import yaml
from sunflare.device import Device
from sunflare.presenter import Presenter
from sunflare.storage import (
    AutoIncrementFilenameProvider,
    StaticFilenameProvider,
    StaticPathProvider,
    StorageDescriptor,
    StorageProxy,
    UUIDFilenameProvider,
    Writer,
)
from sunflare.view import View
from sunflare.virtual import (
    HasShutdown,
    IsInjectable,
    IsProvider,
    VirtualContainer,
)

from ._config import AppConfig, StorageConfig
from .components import (
    _DeviceComponent,
    _DeviceField,
    _PresenterComponent,
    _PresenterField,
    _ViewComponent,
    _ViewField,
)

if TYPE_CHECKING:
    from sunflare.virtual import RedSunConfig
    from typing_extensions import Never, Self

ManifestItems = dict[str, Any]  # maps plugin_id -> class path (str) or dict
PluginType = Union[type[Device], type[Presenter], type[View]]
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
    presenters: dict[str, type[Presenter]]
    views: dict[str, type[View]]


def _assert_never(arg: Never) -> Never:
    raise AssertionError(f"Unhandled case: {arg!r}")


def _check_device_protocol(cls: type) -> TypeGuard[type[Device]]:
    """Check if a class implements the device protocol."""
    if Device in cls.mro():
        return True

    required_methods = ["read_configuration", "describe_configuration"]
    required_properties = ["name", "parent"]

    is_compliant = all(
        hasattr(cls, attr) for attr in [*required_methods, *required_properties]
    )
    if is_compliant:
        Device.register(cls)
    return True


def _check_presenter_protocol(cls: type) -> TypeGuard[type[Presenter]]:
    """Check if a class implements the presenter protocol."""
    if Presenter in cls.mro():
        return True

    # TODO: this check is fragile because it might
    # happen that a class does not store at initialization
    # the devices and so such attribute does not exists at the
    # moment of the check; the best solution is to impose
    # a stricter __instancecheck__ hook at protocol level
    required_attributes = ["devices", "name"]
    is_compliant = all(hasattr(cls, attr) for attr in required_attributes)
    if is_compliant:
        Presenter.register(cls)
    return is_compliant


def _check_view_protocol(cls: type) -> TypeGuard[type[View]]:
    """Check if a class implements the view protocol."""
    if issubclass(cls, View):
        return True

    required_attributes = ["name", "view_position"]
    is_compliant = all([hasattr(cls, attr) for attr in required_attributes])

    if is_compliant:
        View.register(cls)
    return is_compliant


@overload
def _check_plugin_protocol(
    imported_class: type, group: Literal["devices"]
) -> TypeGuard[type[Device]]: ...
@overload
def _check_plugin_protocol(
    imported_class: type, group: Literal["presenters"]
) -> TypeGuard[type[Presenter]]: ...
@overload
def _check_plugin_protocol(
    imported_class: type, group: Literal["views"]
) -> TypeGuard[type[View]]: ...
def _check_plugin_protocol(imported_class: type, group: PLUGIN_GROUPS) -> bool:
    match group:
        case "devices":
            return _check_device_protocol(imported_class)
        case "presenters":
            return _check_presenter_protocol(imported_class)
        case "views":
            return _check_view_protocol(imported_class)
        case _:
            _assert_never(group)


def _build_writer(cfg: StorageConfig, session: str) -> Writer:
    """Build a storage writer from a ``StorageConfig`` mapping.

    Parameters
    ----------
    cfg : StorageConfig
        Storage section from the application configuration.
    session : str
        Session name, used to derive the default storage directory
        (``~/redsun-storage/<session>``).

    Returns
    -------
    Writer
        Configured writer instance ready for injection.
    """
    from pathlib import Path

    backend = cfg.get("backend", "zarr")
    raw_path = cfg.get("base_path")
    if raw_path is None:
        base_dir = Path.home() / "redsun-storage" / session
    else:
        base_dir = Path(raw_path)
    base_dir.mkdir(parents=True, exist_ok=True)
    base_uri = base_dir.as_uri()

    strategy = cfg.get(
        "filename_provider", "auto_increment"
    )  # TODO: expose per-plan override (future PR)

    filename_provider: (
        StaticFilenameProvider | AutoIncrementFilenameProvider | UUIDFilenameProvider
    )
    if strategy == "static":
        filename = cfg.get("filename", "scan")
        filename_provider = StaticFilenameProvider(filename)
    elif strategy == "auto_increment":
        filename_provider = AutoIncrementFilenameProvider()
    else:
        filename_provider = UUIDFilenameProvider()

    path_provider = StaticPathProvider(filename_provider, base_uri=base_uri)

    if backend == "zarr":
        try:
            from sunflare.storage._zarr import ZarrWriter
        except ImportError:
            raise ImportError(
                "The 'zarr' storage backend requires the 'acquire-zarr' package. "
                "Install it with: pip install sunflare[zarr]"
            )
        return ZarrWriter("redsun-writer", path_provider)

    raise ValueError(f"Unknown storage backend {backend!r}. Supported backends: 'zarr'")


class _HasStorageMeta(_ProtocolMeta):
    """Metaclass for ``_HasStorage`` that overrides ``__instancecheck__``.

    Walks ``type(instance).__mro__`` looking for a ``StorageDescriptor``
    on the class itself — not the ``None`` value the descriptor returns
    before injection.  This ensures ``isinstance(device, _HasStorage)``
    is only ``True`` when the device has genuinely opted in to storage.

    TODO: move to ``sunflare.storage`` together with ``_HasStorage``
    in a future sunflare release.
    """

    def __instancecheck__(cls, instance: object) -> bool:
        return any(
            isinstance(vars(c).get("storage"), StorageDescriptor)
            for c in type(instance).__mro__
        )


@runtime_checkable
class _HasStorage(Protocol, metaclass=_HasStorageMeta):
    """Private protocol for devices that have opted in to storage.

    Declares the ``storage`` attribute so that mypy narrows the type
    correctly inside ``_inject_storage`` after the ``isinstance`` check.

    TODO: move to ``sunflare.storage`` in a future sunflare release.
    """

    storage: StorageProxy | None


def _inject_storage(devices: dict[str, Device], writer: Writer) -> None:
    """Inject *writer* into every device that carries a ``StorageDescriptor``."""
    for name, device in devices.items():
        if isinstance(device, _HasStorage):
            device.storage = writer
            logger.debug(f"Injected storage writer into device '{name}'")


T = TypeVar("T")

__all__ = ["AppContainerMeta", "AppContainer"]

logger = logging.getLogger("redsun")

_PLUGIN_META_KEYS: frozenset[str] = frozenset({"plugin_name", "plugin_id"})

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


class AppContainerMeta(type):
    """Metaclass that auto-collects component wrappers from class attributes."""

    _device_components: dict[str, _DeviceComponent]
    _presenter_components: dict[str, _PresenterComponent]
    _view_components: dict[str, _ViewComponent]
    _config_path: Path | None

    def __new__(
        mcs,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        config: str | Path | None = None,
        **kwargs: Any,
    ) -> AppContainerMeta:
        """Create the class and collect component wrappers.

        Parameters
        ----------
        config : str | Path | None
            Path to a YAML configuration file for component kwargs.
        """
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)

        config_path: Path | None = None
        if config is not None:
            config_path = Path(config)
        else:
            for base in bases:
                if hasattr(base, "_config_path") and base._config_path is not None:
                    if isinstance(base._config_path, str):
                        config_path = Path(base._config_path)
                    elif isinstance(base._config_path, Path):
                        config_path = base._config_path
                    config_path = base._config_path
                    break
        cls._config_path = config_path

        devices: dict[str, _DeviceComponent] = {}
        presenters: dict[str, _PresenterComponent] = {}
        views: dict[str, _ViewComponent] = {}

        for base in bases:
            if hasattr(base, "_device_components"):
                devices.update(base._device_components)
            if hasattr(base, "_presenter_components"):
                presenters.update(base._presenter_components)
            if hasattr(base, "_view_components"):
                views.update(base._view_components)

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
            if config_path is not None:
                config_data = _load_yaml(config_path)

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
                            f"Component field '{attr_name}' in {name} has "
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
                            f"'{section_key}' for component field '{attr_name}' in {name}, "
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
                f"Collected from {name}: "
                f"{len(devices)} devices, "
                f"{len(presenters)} presenters, "
                f"{len(views)} views"
            )

        return cls


class AppContainer(metaclass=AppContainerMeta):
    """Application container for MVP architecture."""

    _device_components: ClassVar[dict[str, _DeviceComponent]]
    _presenter_components: ClassVar[dict[str, _PresenterComponent]]
    _view_components: ClassVar[dict[str, _ViewComponent]]

    __slots__ = (
        "_config",
        "_virtual_container",
        "_is_built",
    )

    def __init__(self, *, session: str = "Redsun", frontend: str = "pyqt") -> None:
        self._config: AppConfig = {
            "schema_version": 1.0,
            "session": session,
            "frontend": frontend,
        }
        self._virtual_container: VirtualContainer | None = None
        self._is_built: bool = False

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
    def presenters(self) -> dict[str, Presenter]:
        """Return built presenter instances."""
        if not self._is_built:
            raise RuntimeError("Container not built. Call build() first.")
        return {
            name: comp.instance for name, comp in self._presenter_components.items()
        }

    @property
    def views(self) -> dict[str, View]:
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

    def build(self) -> Self:
        """Instantiate all components in dependency order.

        Build order:

        1. VirtualContainer
        2. Devices
        3. Presenters (register their providers in the VirtualContainer)
        4. Views (inject dependencies from the VirtualContainer)
        """
        if self._is_built:
            logger.warning("Container already built, skipping rebuild")
            return self

        logger.info("Building application container...")

        self._virtual_container = VirtualContainer()

        base_cfg: RedSunConfig = {
            "schema_version": self._config.get("schema_version", 1.0),
            "session": self._config.get("session", "Redsun"),
            "frontend": self._config.get("frontend", "pyqt"),
        }
        self._virtual_container._set_configuration(base_cfg)
        logger.debug("VirtualContainer created")

        # build devices
        built_devices: dict[str, Device] = {}
        for name, device_comp in self._device_components.items():
            try:
                built_devices[name] = device_comp.build()
                logger.debug(f"Device '{name}' built")
            except Exception as e:
                logger.error(f"Failed to build device '{name}': {e}")

        # inject storage writer if configured
        storage_cfg = self._config.get("storage")
        if storage_cfg is not None:
            try:
                writer = _build_writer(
                    storage_cfg, self._config.get("session", "redsun")
                )
                _inject_storage(built_devices, writer)
                logger.debug("Storage writer built and injected")
            except Exception as e:
                logger.error(f"Failed to build storage writer: {e}")

        # build presenters
        for comp_name, presenter_component in self._presenter_components.items():
            try:
                presenter_component.build(built_devices)
            except Exception as e:
                logger.error(f"Failed to build presenter '{comp_name}': {e}")
                raise

        # build views
        for comp_name, view_component in self._view_components.items():
            try:
                view_component.build()
            except Exception as e:
                logger.error(f"Failed to build view '{comp_name}': {e}")
                raise

        # register providers from presenters and views
        all_components: dict[str, _PresenterComponent | _ViewComponent] = {
            **self._presenter_components,
            **self._view_components,
        }
        for comp_name, component in all_components.items():
            if isinstance(component.instance, IsProvider):
                component.instance.register_providers(self._virtual_container)

        # inject dependencies into presenters and views
        for comp_name, component in all_components.items():
            if isinstance(component.instance, IsInjectable):
                component.instance.inject_dependencies(self._virtual_container)

        self._is_built = True
        logger.info(
            f"Container built: "
            f"{len(self._device_components)} devices, "
            f"{len(self._presenter_components)} presenters, "
            f"{len(self._view_components)} views"
        )

        return self

    def shutdown(self) -> None:
        """Shutdown all presenters that implement ``HasShutdown``."""
        if not self._is_built:
            return

        for name, comp in self._presenter_components.items():
            if isinstance(comp.instance, HasShutdown):
                try:
                    comp.instance.shutdown()
                except Exception as e:
                    logger.error(f"Error shutting down presenter '{name}': {e}")

        self._is_built = False
        logger.info("Container shutdown complete")

    def run(self) -> None:
        """Build if needed and start the application."""
        if not self._is_built:
            self.build()

        frontend = self._config.get("frontend", "pyqt")
        logger.info(f"Starting application with frontend: {frontend}")

    @classmethod
    def from_config(cls, config_path: str) -> AppContainer:
        """Build a container dynamically from a YAML configuration file."""
        config, plugin_types = cls._load_configuration(config_path)

        namespace: dict[str, Any] = {}

        for name, device_class in plugin_types["devices"].items():
            cfg_kwargs = {
                k: v
                for k, v in config.get("devices", {}).get(name, {}).items()
                if k not in _PLUGIN_META_KEYS
            }
            namespace[name] = _DeviceComponent(device_class, name, **cfg_kwargs)

        for name, presenter_class in plugin_types["presenters"].items():
            cfg_kwargs = {
                k: v
                for k, v in config.get("presenters", {}).get(name, {}).items()
                if k not in _PLUGIN_META_KEYS
            }
            namespace[name] = _PresenterComponent(presenter_class, name, **cfg_kwargs)

        for name, view_class in plugin_types["views"].items():
            cfg_kwargs = {
                k: v
                for k, v in config.get("views", {}).get(name, {}).items()
                if k not in _PLUGIN_META_KEYS
            }
            namespace[name] = _ViewComponent(view_class, name, **cfg_kwargs)

        frontend = config.get("frontend", "pyqt")
        base_class = _resolve_frontend_container(frontend)

        DynamicApp: type[AppContainer] = type("DynamicApp", (base_class,), namespace)

        instance = DynamicApp(
            session=config.get("session", "Redsun"),
            frontend=frontend,
        )

        storage_cfg = config.get("storage")
        if storage_cfg is not None:
            instance._config["storage"] = storage_cfg

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
                        "%s exists, but does not implement any known protocol.",
                        imported_class,
                    )
                    continue

                plugins.append((name, imported_class))

        return plugins


__all__ = ["AppContainerMeta", "AppContainer", "Frontend"]
