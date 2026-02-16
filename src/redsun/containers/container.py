"""Application container for MVP architecture.

Provides :class:`AppContainer` and its metaclass :class:`AppContainerMeta`
for declarative component registration and dependency-ordered instantiation.
"""

from __future__ import annotations

import logging
from importlib import import_module
from typing import TYPE_CHECKING, Any, ClassVar

from dependency_injector import containers, providers
from sunflare.virtual import HasShutdown, IsInjectable, IsProvider

from redsun.plugins import load_configuration

from .components import DeviceComponent, PresenterComponent, ViewComponent

if TYPE_CHECKING:
    from sunflare.device import Device
    from sunflare.presenter import Presenter
    from sunflare.view import View
    from sunflare.virtual import VirtualBus

__all__ = ["AppContainerMeta", "AppContainer"]

logger = logging.getLogger("redsun")

_PLUGIN_META_KEYS: frozenset[str] = frozenset({"plugin_name", "plugin_id"})

_FRONTEND_CONTAINERS: dict[str, str] = {
    "pyqt": "redsun.containers.qt_container.QtAppContainer",
    "pyside": "redsun.containers.qt_container.QtAppContainer",
}


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
            f"Unknown frontend {frontend!r}. "
            f"Supported: {sorted(_FRONTEND_CONTAINERS)}"
        )
    module_path, class_name = dotted_path.rsplit(".", 1)
    module = import_module(module_path)
    return getattr(module, class_name)  # type: ignore[no-any-return]


class AppContainerMeta(type):
    """Metaclass that auto-collects component wrappers from class attributes.

    When a new class is created with this metaclass, it scans the namespace
    for :class:`DeviceComponent`, :class:`PresenterComponent`, and
    :class:`ViewComponent` instances, collecting them into class-level
    dictionaries.  Components from base classes are inherited and can be
    overridden.
    """

    _device_components: dict[str, DeviceComponent]
    _presenter_components: dict[str, PresenterComponent]
    _view_components: dict[str, ViewComponent]

    def __new__(  # noqa: D102
        mcs,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        **kwargs: Any,
    ) -> AppContainerMeta:
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)

        # Inherit components from base classes
        devices: dict[str, DeviceComponent] = {}
        presenters: dict[str, PresenterComponent] = {}
        views: dict[str, ViewComponent] = {}

        for base in bases:
            if hasattr(base, "_device_components"):
                devices.update(base._device_components)
            if hasattr(base, "_presenter_components"):
                presenters.update(base._presenter_components)
            if hasattr(base, "_view_components"):
                views.update(base._view_components)

        # Overlay with components declared in current namespace
        for attr_name, attr_value in namespace.items():
            if attr_name.startswith("_"):
                continue

            if isinstance(attr_value, DeviceComponent):
                devices[attr_value.name] = attr_value
            elif isinstance(attr_value, PresenterComponent):
                presenters[attr_value.name] = attr_value
            elif isinstance(attr_value, ViewComponent):
                views[attr_value.name] = attr_value

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

    Uses ``dependency-injector`` for IoC between presenter and view layers.
    ``VirtualBus`` signals are reserved for runtime communication.

    Parameters
    ----------
    **config : Any
        Configuration options.  Common keys:

        - ``session`` : str - Session name (default: ``"Redsun"``)
        - ``frontend`` : str - Frontend type (default: ``"pyqt"``)
    """

    # Populated by metaclass
    _device_components: ClassVar[dict[str, DeviceComponent]]
    _presenter_components: ClassVar[dict[str, PresenterComponent]]
    _view_components: ClassVar[dict[str, ViewComponent]]

    __slots__ = (
        "_config",
        "_virtual_bus",
        "_di_container",
        "_is_built",
    )

    def __init__(self, **config: Any) -> None:
        self._config: dict[str, Any] = {
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
        from sunflare.virtual import VirtualBus

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

        # 3. Build devices
        built_devices: dict[str, Device] = {}
        for name, device in self._device_components.items():
            try:
                built_devices[name] = device.build()
                logger.debug(f"Device '{name}' built")
            except Exception as e:
                logger.error(f"Failed to build device '{name}': {e}")

        # 4. Build presenters and register their providers
        for name, presenter_component in self._presenter_components.items():
            try:
                presenter = presenter_component.build(built_devices, self._virtual_bus)
                if isinstance(presenter, IsProvider):
                    presenter.register_providers(self._di_container)
            except Exception as e:
                logger.error(f"Failed to build presenter '{name}': {e}")
                raise

        # 5. Build views and inject dependencies
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
        """Shutdown all components that implement ``HasShutdown``."""
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
        config, plugin_types = load_configuration(config_path)

        namespace: dict[str, Any] = {}

        # Create device components
        for name, device_cfg in config.get("models", {}).items():
            device_class = plugin_types["models"][name]
            kwargs = {k: v for k, v in device_cfg.items() if k not in _PLUGIN_META_KEYS}
            namespace[name] = DeviceComponent(device_class, name, **kwargs)

        # Create presenter components
        for name, presenter_cfg in config.get("controllers", {}).items():
            presenter_class = plugin_types["controllers"][name]
            kwargs = {
                k: v for k, v in presenter_cfg.items() if k not in _PLUGIN_META_KEYS
            }
            namespace[name] = PresenterComponent(presenter_class, name, **kwargs)

        # Create view components
        for name, view_cfg in config.get("views", {}).items():
            view_class = plugin_types["views"][name]
            kwargs = {k: v for k, v in view_cfg.items() if k not in _PLUGIN_META_KEYS}
            namespace[name] = ViewComponent(view_class, name, **kwargs)

        # Resolve the correct base class for the configured frontend
        frontend = config.get("frontend", "pyqt")
        base_class = _resolve_frontend_container(frontend)

        DynamicApp: type[AppContainer] = type("DynamicApp", (base_class,), namespace)

        return DynamicApp(
            session=config.get("session", "Redsun"),
            frontend=frontend,
        )
