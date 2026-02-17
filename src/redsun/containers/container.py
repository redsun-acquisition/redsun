"""Application container for MVP architecture.

Provides `AppContainer` and its metaclass `AppContainerMeta`
for declarative component registration and dependency-ordered instantiation.
"""

from __future__ import annotations

import logging
import sys
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
    Union,
    get_type_hints,
    overload,
)

import yaml
from dependency_injector import containers, providers
from sunflare.virtual import HasShutdown, IsInjectable, IsProvider, VirtualBus
from typing_extensions import dataclass_transform

from .components import (
    RedSunConfig,
    _ComponentField,
    _DeviceComponent,
    _PresenterComponent,
    _ViewComponent,
    component,
)

if TYPE_CHECKING:
    from typing_extensions import Never

from sunflare.device import Device
from sunflare.presenter import Presenter
from sunflare.view import View

ManifestItems = dict[str, dict[str, str]]
PluginType = Union[type[Device], type[Presenter], type[View]]
PLUGIN_GROUPS = Literal["devices", "presenters", "views"]


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

    required_attributes = ["devices", "virtual_bus"]
    is_compliant = all(hasattr(cls, attr) for attr in required_attributes)
    if is_compliant:
        Presenter.register(cls)
    return is_compliant


def _check_view_protocol(cls: type) -> TypeGuard[type[View]]:
    """Check if a class implements the view protocol."""
    if issubclass(cls, View):
        return True
    is_compliant = hasattr(cls, "virtual_bus")

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


T = TypeVar("T")

__all__ = ["AppContainerMeta", "AppContainer"]

logger = logging.getLogger("redsun")

_PLUGIN_META_KEYS: frozenset[str] = frozenset({"plugin_name", "plugin_id"})

_FRONTEND_CONTAINERS: dict[str, str] = {
    "pyqt": "redsun.containers.qt_container.QtAppContainer",
    "pyside": "redsun.containers.qt_container.QtAppContainer",
}


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML file and return its contents as a dictionary.

    Parameters
    ----------
    path : Path
        Path to the YAML configuration file.

    Returns
    -------
    dict[str, Any]
        Parsed YAML contents.

    Raises
    ------
    FileNotFoundError
        If the file does not exist.
    """
    with open(path) as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise TypeError(
            f"Expected a YAML mapping at top level in {path}, got {type(data).__name__}"
        )
    required_keys = RedSunConfig.__required_keys__
    missing = required_keys - data.keys()
    if missing:
        raise KeyError(
            f"Configuration file {path} is missing required keys: "
            f"{', '.join(sorted(missing))}"
        )
    return data


def _resolve_frontend_container(frontend: str) -> type[AppContainer]:
    """Resolve a frontend string to the appropriate container class.

    Parameters
    ----------
    frontend : str
        Frontend type from configuration (e.g. ``"pyqt"``, ``"pyside"``).

    Returns
    -------
    type[AppContainer]
        The container subclass for the given frontend.

    Raises
    ------
    ValueError
        If the frontend type is not recognized.
    """
    dotted_path = _FRONTEND_CONTAINERS.get(frontend)
    if dotted_path is None:
        raise ValueError(
            f"Unknown frontend {frontend!r}. Supported: {sorted(_FRONTEND_CONTAINERS)}"
        )
    module_path, class_name = dotted_path.rsplit(".", 1)
    module = import_module(module_path)
    ret_cls: type[AppContainer] = getattr(module, class_name)
    return ret_cls


@dataclass_transform(field_specifiers=(component,))
class AppContainerMeta(type):
    """Metaclass that auto-collects component wrappers from class attributes.

    When a new class is created with this metaclass, it scans the namespace
    for `_DeviceComponent`, `_PresenterComponent`, and
    `_ViewComponent` instances, collecting them into class-level
    dictionaries.  Components from base classes are inherited and can be
    overridden.

    Annotated fields using `component` are also resolved: the type
    annotation provides the component class and the attribute name becomes
    the component name.

    Parameters
    ----------
    config : str | Path | None
        Path to a YAML configuration file. If provided, component fields
        with ``from_config`` set will pull their kwargs from this file.
    """

    _device_components: dict[str, _DeviceComponent]
    _presenter_components: dict[str, _PresenterComponent]
    _view_components: dict[str, _ViewComponent]
    _config_path: Path | None

    def __new__(  # noqa: D102
        mcs,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        config: str | Path | None = None,
        **kwargs: Any,
    ) -> AppContainerMeta:
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)

        # Store config path on the class
        config_path: Path | None = None
        if config is not None:
            config_path = Path(config)
        else:
            # Check base classes for an inherited config path
            for base in bases:
                if hasattr(base, "_config_path") and base._config_path is not None:
                    config_path = base._config_path
                    break
        cls._config_path = config_path

        # Inherit components from base classes
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

        # Overlay with explicit component wrappers declared in current namespace
        for attr_name, attr_value in namespace.items():
            if attr_name.startswith("_"):
                continue

            if isinstance(attr_value, _DeviceComponent):
                devices[attr_value.name] = attr_value
            elif isinstance(attr_value, _PresenterComponent):
                presenters[attr_value.name] = attr_value
            elif isinstance(attr_value, _ViewComponent):
                views[attr_value.name] = attr_value

        # Resolve component() field declarations from annotations
        annotations = namespace.get("__annotations__", {})
        component_fields = {
            attr_name
            for attr_name in annotations
            if not attr_name.startswith("_")
            and isinstance(namespace.get(attr_name), _ComponentField)
        }

        if component_fields:
            # Load container-level config if a config path is present
            config_data: dict[str, Any] = {}
            if config_path is not None:
                config_data = _load_yaml(config_path)

            try:
                hints = get_type_hints(cls)
            except NameError:
                # Annotations may reference names from an enclosing local
                # scope (e.g. a class defined inside a function).  Fall back
                # to the caller's frame locals for resolution.
                frame = sys._getframe(1)
                hints = get_type_hints(cls, localns=frame.f_locals)

            for attr_name in component_fields:
                field: _ComponentField = namespace[attr_name]
                component_cls = hints.get(attr_name)
                if component_cls is None:
                    logger.warning(
                        f"Could not resolve type hint for component "
                        f"field '{attr_name}' in {name}, skipping"
                    )
                    continue

                # Merge kwargs: config file values as base, inline as override
                kwargs = field.kwargs
                if field.from_config is not None:
                    if not config_data:
                        raise TypeError(
                            f"Component field '{attr_name}' in {name} has "
                            f"from_config set but no config path was "
                            f"provided to the container class"
                        )

                    # Map layer to config section key
                    layer_to_section = {
                        "device": "devices",
                        "presenter": "presenters",
                        "view": "views",
                    }
                    section_key = layer_to_section[field.layer]
                    section_data: dict[str, Any] = config_data.get(section_key, {})
                    cfg_section = section_data.get(field.from_config)

                    if cfg_section is None:
                        logger.warning(
                            f"No config section '{field.from_config}' found in "
                            f"'{section_key}' for component field '{attr_name}' in {name}, "
                            f"using inline kwargs only"
                        )
                        kwargs = field.kwargs
                    else:
                        kwargs = {**cfg_section, **field.kwargs}
                else:
                    kwargs = field.kwargs

                wrapper: _DeviceComponent | _PresenterComponent | _ViewComponent
                match field.layer:
                    case "device":
                        wrapper = _DeviceComponent(
                            component_cls, attr_name, field.alias, **kwargs
                        )
                        devices[attr_name] = wrapper
                    case "presenter":
                        wrapper = _PresenterComponent(
                            component_cls, attr_name, None, **kwargs
                        )
                        presenters[attr_name] = wrapper
                    case "view":
                        wrapper = _ViewComponent(
                            component_cls, attr_name, None, **kwargs
                        )
                        views[attr_name] = wrapper
                    case _:
                        _assert_never(field.layer)
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
    """Application container for MVP architecture.

    Parameters
    ----------
    **config : dict[str, Any]
        Configuration options.  Common keys:

        - ``session`` : str - Session name (default: ``"Redsun"``)
        - ``frontend`` : str - Frontend type (default: ``"pyqt"``)
    """

    # Populated by metaclass
    _device_components: ClassVar[dict[str, _DeviceComponent]]
    _presenter_components: ClassVar[dict[str, _PresenterComponent]]
    _view_components: ClassVar[dict[str, _ViewComponent]]

    __slots__ = (
        "_config",
        "_virtual_bus",
        "_di_container",
        "_is_built",
    )

    def __init__(self, **config: Any) -> None:
        self._config = {
            "session": config.get("session", "Redsun"),
            "frontend": config.get("frontend", "pyqt"),
            **config,
        }
        self._virtual_bus: VirtualBus | None = None
        self._di_container: containers.DynamicContainer | None = None
        self._is_built: bool = False

    @property
    def config(self) -> dict[str, Any]:
        """Return the configuration dictionary."""
        return self._config

    @property
    def devices(self) -> dict[str, Device]:
        """Return built device instances.

        Raises
        ------
        RuntimeError
            If the container has not been built yet.
        """
        if not self._is_built:
            raise RuntimeError("Container not built. Call build() first.")
        return {name: comp.instance for name, comp in self._device_components.items()}

    @property
    def presenters(self) -> dict[str, Presenter]:
        """Return built presenter instances.

        Raises
        ------
        RuntimeError
            If the container has not been built yet.
        """
        if not self._is_built:
            raise RuntimeError("Container not built. Call build() first.")
        return {
            name: comp.instance for name, comp in self._presenter_components.items()
        }

    @property
    def views(self) -> dict[str, View]:
        """Return built view instances.

        Raises
        ------
        RuntimeError
            If the container has not been built yet.
        """
        if not self._is_built:
            raise RuntimeError("Container not built. Call build() first.")
        return {name: comp.instance for name, comp in self._view_components.items()}

    @property
    def virtual_bus(self) -> VirtualBus:
        """Return the virtual bus instance.

        Raises
        ------
        RuntimeError
            If the container has not been built yet.
        """
        if self._virtual_bus is None:
            raise RuntimeError("Container not built. Call build() first.")
        return self._virtual_bus

    @property
    def di_container(self) -> containers.DynamicContainer:
        """Return the dependency-injector container.

        Raises
        ------
        RuntimeError
            If the container has not been built yet.
        """
        if self._di_container is None:
            raise RuntimeError("Container not built. Call build() first.")
        return self._di_container

    @property
    def is_built(self) -> bool:
        """Return whether the container has been built."""
        return self._is_built

    def build(self) -> AppContainer:
        """Instantiate all components in dependency order.

        Build order:

        1. VirtualBus
        2. DI Container
        3. Devices
        4. Presenters (register their providers in the DI container)
        5. Views (inject dependencies from the DI container)

        Returns
        -------
        AppContainer
            Self, for method chaining.
        """
        if self._is_built:
            logger.warning("Container already built, skipping rebuild")
            return self

        logger.info("Building application container...")

        # 1. Virtual bus for runtime signals
        self._virtual_bus = VirtualBus()
        logger.debug("Virtual bus created")

        # 2. DI container for presenter -> view injection
        self._di_container = containers.DynamicContainer()
        self._di_container.config = providers.Configuration()
        self._di_container.config.from_dict(self._config)
        logger.debug("DI container created")

        # build devices
        built_devices: dict[str, Device] = {}
        for name, device in self._device_components.items():
            try:
                built_devices[name] = device.build()
                logger.debug(f"Device '{name}' built")
            except Exception as e:
                logger.error(f"Failed to build device '{name}': {e}")

        # build presenters and register their providers
        for name, presenter_component in self._presenter_components.items():
            try:
                presenter = presenter_component.build(built_devices, self._virtual_bus)
                if isinstance(presenter, IsProvider):
                    presenter.register_providers(self._di_container)
            except Exception as e:
                logger.error(f"Failed to build presenter '{name}': {e}")
                raise

        # build views and inject dependencies
        for name, view_component in self._view_components.items():
            try:
                view = view_component.build(self._virtual_bus)
                if isinstance(view, IsInjectable):
                    view.inject_dependencies(self._di_container)
            except Exception as e:
                logger.error(f"Failed to build view '{name}': {e}")
                raise

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
        """Build if needed and start the application.

        Subclasses override this to provide frontend-specific launch logic.
        """
        if not self._is_built:
            self.build()

        frontend = self._config.get("frontend", "pyqt")
        logger.info(f"Starting application with frontend: {frontend}")

    @classmethod
    def from_config(cls, config_path: str) -> AppContainer:
        """Build a container dynamically from a YAML configuration file.

        Reads the configuration, discovers plugins via entry points,
        and returns an unbuilt container of the appropriate frontend type.

        Parameters
        ----------
        config_path : str
            Path to the YAML configuration file.

        Returns
        -------
        AppContainer
            A configured (but unbuilt) container instance.
        """
        config, plugin_types = cls._load_configuration(config_path)

        namespace: dict[str, Any] = {}

        # Create device components
        for name, device_cfg in config.get("devices", {}).items():
            device_class = plugin_types["devices"][name]
            kwargs = {k: v for k, v in device_cfg.items() if k not in _PLUGIN_META_KEYS}
            namespace[name] = _DeviceComponent(device_class, name, None, **kwargs)

        # Create presenter components
        for name, presenter_cfg in config.get("presenters", {}).items():
            presenter_class = plugin_types["presenters"][name]
            kwargs = {
                k: v for k, v in presenter_cfg.items() if k not in _PLUGIN_META_KEYS
            }
            namespace[name] = _PresenterComponent(presenter_class, name, None, **kwargs)

        # Create view components
        for name, view_cfg in config.get("views", {}).items():
            view_class = plugin_types["views"][name]
            kwargs = {k: v for k, v in view_cfg.items() if k not in _PLUGIN_META_KEYS}
            namespace[name] = _ViewComponent(view_class, name, None, **kwargs)

        # Resolve the correct base class for the configured frontend
        frontend = config.get("frontend", "pyqt")
        base_class = _resolve_frontend_container(frontend)

        DynamicApp: type[AppContainer] = type("DynamicApp", (base_class,), namespace)

        return DynamicApp(
            session=config.get("session", "Redsun"),
            frontend=frontend,
        )

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
                # mypy complains because it can't verify the type of plugin_cls;
                # but it is guaranteed to be correct at runtime because we're
                # doing a lot of manual checks so just ignore it
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
        """Load plugin classes for a given group."""
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

                if not _check_plugin_protocol(imported_class, group):
                    logger.error(
                        "%s exists, but does not implement any known protocol.",
                        imported_class,
                    )
                    continue

                plugins.append((name, imported_class))

        return plugins
