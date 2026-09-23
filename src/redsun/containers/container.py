"""`AppContainer`, which declares a session's components and builds them in order."""

from __future__ import annotations

import asyncio
import importlib.util
import logging
from contextlib import suppress

# resolved at runtime: the ClassVar annotation below is evaluated by ruff's
# runtime-evaluated rules and by anything calling get_type_hints on a subclass
from importlib import import_module
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    TypeVar,
    cast,
)

from redsun.aio import get_shared_loop, run_coro
from redsun.catalog import CATALOG, CatalogAddress
from redsun.containers.components import (
    _ComponentField,
    _DeviceComponent,
    _DeviceField,
    _HookField,
    _NotBuilt,
    _PresenterComponent,
    _PresenterField,
    _ServiceComponent,
    _ViewComponent,
    _ViewField,
)
from redsun.log import SessionFileHandler, add_handler, remove_handler, set_level
from redsun.path_provider import PATH_PROVIDER, SessionPathProvider
from redsun.virtual import (
    ComponentNotBuilt,
    Connection,
    HasShutdown,
    IsInjectable,
    IsProvider,
    VirtualContainer,
    WiringError,
)

from ..services._transports import CHANNEL_ACCESS, TRANSPORTS
from ._config import (
    COMPONENT_SECTIONS,
    TRANSPORT_KEY,
    AppConfig,
    CatalogConfig,
    Frontend,
    StorageConfig,
    checked_transport,
    declared_transport,
    load_yaml,
    refuse_unresolved_fields,
    transport_of,
)
from ._hooks import (
    HookError,
    build_hook_provider,
    distinct,
    parse_hook_specs,
    resolve_hooks,
)
from ._manifest import discover
from ._plugins import PLUGIN_GROUPS, PLUGIN_META_KEYS, load_configuration, services_of

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence
    from typing import Final, Self, TypeAlias

    from ophyd_async.core import Device
    from psygnal import SignalInstance
    from tiled.server.simple import SimpleTiledServer

    from redsun.containers.components import _ComponentBase
    from redsun.presenter import PPresenter
    from redsun.services import Service
    from redsun.view import PView
    from redsun.virtual import RedSunConfig

    from ..virtual._wiring import SlotThread

    _ComponentFactory: TypeAlias = Callable[..., _ComponentBase[Any]]


T = TypeVar("T")

logger = logging.getLogger("redsun")

CONNECT_TIMEOUT: Final = 10.0
"""Seconds the build waits for each device it connects."""

PATH_PROVIDER_PORT: Final = "path_provider"
"""Name the session's path provider is wired under."""


def _require_tiled() -> None:
    """Raise if a session asks for a catalog and the ``tiled`` extra is missing."""
    missing = [
        package
        for package in ("tiled", "ome_tiled", "bluesky_tiled_plugins")
        if importlib.util.find_spec(package) is None
    ]
    if not missing:
        return
    raise RuntimeError(
        "this session's 'storage' section has a 'catalog' key and "
        f"{', '.join(repr(package) for package in missing)} not installed. "
        "Install them with 'pip install redsun[tiled]', or drop the key. "
        "The extra installs nothing on Python 3.14, which tiled does not "
        "support yet."
    )


def _silent(step: str) -> None:
    """Ignore a build step's name.

    `AppContainer` reports progress here when no hook asked for it, so the
    build has one path either way.
    """


_FRONTEND_CONTAINERS: dict[str, str] = {
    "pyqt": "redsun.containers.qt._container.QtAppContainer",
    "pyside": "redsun.containers.qt._container.QtAppContainer",
}


def _resolve_frontend_container(frontend: str) -> type[AppContainer]:
    """Return the container class of a frontend name."""
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
    """Application container of a DVP session.

    Parameters
    ----------
    session : str
        Session display name.
    frontend : str
        Frontend toolkit identifier.
    log_level : int or str, optional
        Level of the ``redsun`` logger, as a `logging` constant or a level
        name. Unchanged when not given.
    """

    __slots__ = (
        "_built",
        "_built_devices",
        "_catalog",
        "_components",
        "_config",
        "_failed",
        "_failed_services",
        "_hook_by_moment",
        "_hooks",
        "_is_built",
        "_path_provider",
        "_report",
        "_service_logs",
        "_services",
        "_services_started",
        "_session_log",
        "_virtual_container",
    )

    transport: str = CHANNEL_ACCESS
    """What the session's services speak, one for all of them.

    A session file names it under ``services``, which wins over this.
    """

    _service_components: ClassVar[dict[str, _ServiceComponent]] = {}
    _device_components: ClassVar[dict[str, _DeviceComponent]] = {}
    _presenter_components: ClassVar[dict[str, _PresenterComponent]] = {}
    _view_components: ClassVar[dict[str, _ViewComponent]] = {}
    _component_fields: ClassVar[dict[str, _ComponentField]] = {}
    """Every ``declare_*`` field of this container and its bases.

    Kept after class creation, so a subclass with its own ``config`` resolves
    inherited fields against its own file.
    """

    _config_paths: ClassVar[tuple[Path, ...]] = ()
    """The configuration files this container reads, in layering order.

    A subclass's ``config`` is appended to its bases' files, so a file shared
    by several sessions sits under each session's own.
    """

    BUILD_STEPS: ClassVar[tuple[str, ...]] = (
        "services",
        "virtual container",
        "devices",
        "connect",
        "presenters",
        "views",
        "providers",
        "wiring",
        "injection",
    )
    """The steps `build` announces, in order.

    Each is reported when it starts, so a progress display can size itself from
    this tuple.
    """

    _hook_keys: ClassVar[Mapping[str, type]] = {}
    """The hook points this container calls, in order.

    A key is the method the point calls, which names the point in a container
    class body and in the ``hooks`` section. Empty here: every hook point
    belongs to a toolkit, whose container declares it.
    """

    _hook_providers: ClassVar[dict[str, object]] = {}
    """The providers declared on this container class, by hook point.

    Built when the class is created, so an instance declared at two points
    serves both. A subclass inherits its bases' providers.
    """

    def __init_subclass__(
        cls,
        config: str | Path | Sequence[str | Path] | None = None,
        **kwargs: Any,
    ) -> None:
        """Collect the component declarations of the class body.

        Parameters
        ----------
        config : str | Path | Sequence[str | Path] | None
            YAML file of component keyword arguments, or several layered in
            order. They are read after the bases' files, and a later file wins
            a shared key.
        """
        super().__init_subclass__(**kwargs)

        declared = (
            []
            if config is None
            else [config]
            if isinstance(config, (str, Path))
            else list(config)
        )
        inherited: list[Path] = []
        for base in cls.__bases__:
            if issubclass(base, AppContainer):
                inherited.extend(base._config_paths)
        # a base named twice through two paths of the hierarchy contributes its
        # files once, in the order the first path reached them
        seen: dict[Path, None] = {}
        for path in (*inherited, *(Path(entry) for entry in declared)):
            seen.setdefault(path, None)
        cls._config_paths = tuple(seen)

        services: dict[str, _ServiceComponent] = {}
        devices: dict[str, _DeviceComponent] = {}
        presenters: dict[str, _PresenterComponent] = {}
        views: dict[str, _ViewComponent] = {}

        for base in cls.__bases__:
            if issubclass(base, AppContainer):
                services.update(base._service_components)
                devices.update(base._device_components)
                presenters.update(base._presenter_components)
                views.update(base._view_components)

        namespace = vars(cls)

        # a session file declares services the way it declares anything else,
        # and the class body may add to or replace what it names
        if cls._config_paths:
            with suppress(Exception):
                from_file = services_of(load_yaml(cls._config_paths), discover())
                for name, declared_kwargs in from_file.items():
                    declaration = _ServiceComponent(name, **declared_kwargs)
                    declaration.create()
                    services[name] = declaration

        for attr_name, attr_value in namespace.items():
            if attr_name.startswith("_"):
                continue

            if attr_name == TRANSPORT_KEY and isinstance(
                attr_value,
                (
                    _ServiceComponent,
                    _DeviceComponent,
                    _PresenterComponent,
                    _ViewComponent,
                ),
            ):
                raise TypeError(
                    f"{cls.__name__} names a component {TRANSPORT_KEY!r}, which is "
                    f"what the services of a session say they speak. Name it "
                    f"something else."
                )

            if isinstance(attr_value, _ServiceComponent):
                # made once here so that keywords a Service refuses are refused
                # as the class is created; raised from __set_name__, Python 3.11
                # would wrap the error in a RuntimeError
                attr_value.create()
                services[attr_value.name] = attr_value
            elif isinstance(attr_value, _DeviceComponent):
                devices[attr_value.name] = attr_value
            elif isinstance(attr_value, _PresenterComponent):
                presenters[attr_value.name] = attr_value
            elif isinstance(attr_value, _ViewComponent):
                views[attr_value.name] = attr_value

        cls.transport = checked_transport(
            declared_transport(cls._config_paths, cls.transport),
            f"{cls.__name__}'s services",
        )

        component_fields: dict[str, _ComponentField] = {}
        for base in cls.__bases__:
            if issubclass(base, AppContainer):
                component_fields.update(base._component_fields)
        component_fields.update(
            {
                attr_name: value
                for attr_name, value in namespace.items()
                if not attr_name.startswith("_") and isinstance(value, _ComponentField)
            }
        )
        cls._component_fields = component_fields

        if component_fields:
            config_data: dict[str, Any] = {}
            if cls._config_paths:
                config_data = load_yaml(cls._config_paths)

            _section_key: dict[type, str] = {
                _DeviceField: "devices",
                _PresenterField: "presenters",
                _ViewField: "views",
            }

            for attr_name, field in component_fields.items():
                kw = field.kwargs
                if field.from_config is not None and config_data:
                    section_key = _section_key[type(field)]
                    # a section written with nothing under it parses as None
                    section_data: dict[str, Any] = config_data.get(section_key) or {}
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

        cls._service_components = services
        cls._device_components = devices
        cls._presenter_components = presenters
        cls._view_components = views

        hook_providers: dict[str, object] = {}
        for base in cls.__bases__:
            if issubclass(base, AppContainer):
                hook_providers.update(base._hook_providers)

        hook_fields = {
            attr_name: value
            for attr_name, value in namespace.items()
            if isinstance(value, _HookField)
        }
        for attr_name, hook_field in hook_fields.items():
            provider = build_hook_provider(
                cls.__name__, cls._hook_keys, attr_name, hook_field
            )
            hook_providers[attr_name] = provider
            setattr(cls, attr_name, provider)
        cls._hook_providers = hook_providers

        if devices or presenters or views:
            logger.debug(
                f"Collected from {cls.__name__}: "
                f"{len(devices)} devices, "
                f"{len(presenters)} presenters, "
                f"{len(views)} views"
            )

    def __init__(
        self,
        *,
        session: str = "Redsun",
        frontend: str = "pyqt",
        log_level: int | str | None = None,
    ) -> None:
        refuse_unresolved_fields(
            type(self).__name__,
            type(self)._config_paths,
            type(self)._component_fields,
        )
        if log_level is not None:
            set_level(log_level)
        self._config: AppConfig = {
            "schema_version": 1.0,
            "session": session,
            "frontend": frontend,
        }
        self._virtual_container: VirtualContainer | None = None
        self._path_provider: SessionPathProvider | None = None
        self._catalog: SimpleTiledServer | None = None
        self._hooks: tuple[object, ...] | None = None
        self._hook_by_moment: dict[str, object] = {}
        self._is_built: bool = False
        # what this container built, keyed by the declaration it was built
        # from. The declaration registries are class attributes shared by every
        # container of the class; this is per container, so the objects go when
        # it does and the next container starts from nothing.
        self._built: dict[_ComponentBase[Any], Any] = {}
        # what the build could not make, by component name, so that a phase
        # after the one that failed can tell a component that is not there
        # from a name that was never declared
        self._failed: dict[str, BaseException] = {}
        self._built_devices: dict[str, Device] = {}
        self._components: dict[str, _ComponentBase[Any]] = {
            **self._presenter_components,
            **self._view_components,
        }
        self._report: Callable[[str], None] = _silent
        # a container launches and stops processes of its own, so each one
        # makes its services from the declarations the class shares
        self._services: dict[str, Service] = {
            name: declaration.create(self.transport)
            for name, declaration in self._service_components.items()
        }
        self._failed_services: dict[str, BaseException] = {}
        self._services_started: bool = False

        # In the declarative subclass path (class MyApp(QtAppContainer, config=...))
        # the metaclass loads the YAML only to resolve component kwargs and never
        # populates _config with top-level sections such as 'storage', 'session',
        # or 'schema_version'.  We read those here so that build() sees the same
        # state as the from_config() path, which sets them explicitly.
        config_paths: tuple[Path, ...] = getattr(type(self), "_config_paths", ())
        if config_paths:
            try:
                yaml_data = load_yaml(config_paths)
            except Exception as e:  # noqa: BLE001 - unreadable config falls back to defaults
                named = ", ".join(str(path) for path in config_paths)
                logger.warning(f"Could not read config file(s) {named}: {e}")
                yaml_data = {}
            for key, value in yaml_data.items():
                if key not in COMPONENT_SECTIONS:
                    self._config[key] = value  # type: ignore[literal-required]

        self._session_log: SessionFileHandler | None = None
        self._service_logs: dict[str, SessionFileHandler] = {}
        self._open_session_log()

    @property
    def config(self) -> AppConfig:
        """Return the application configuration."""
        return self._config

    def _built_of(self, declared: Mapping[str, _ComponentBase[T]]) -> dict[str, T]:
        """Return what this container built from *declared*, by name.

        A declaration not reached or failed is absent, so the mapping can be
        shorter than *declared*.
        """
        return {
            name: cast("T", self._built[comp])
            for name, comp in declared.items()
            if comp in self._built
        }

    @property
    def devices(self) -> dict[str, Device]:
        """Return the built devices."""
        if not self._is_built:
            raise RuntimeError("Container not built. Call build() first.")
        return self._built_of(self._device_components)

    @property
    def presenters(self) -> dict[str, PPresenter]:
        """Return the built presenters."""
        if not self._is_built:
            raise RuntimeError("Container not built. Call build() first.")
        return self._built_of(self._presenter_components)

    @property
    def views(self) -> dict[str, PView]:
        """Return the built views."""
        if not self._is_built:
            raise RuntimeError("Container not built. Call build() first.")
        return self._built_of(self._view_components)

    @property
    def services(self) -> dict[str, Service]:
        """Return the container's services, started or not."""
        return dict(self._services)

    @property
    def path_provider(self) -> SessionPathProvider:
        """Return the session's path provider, shared by every device taking one."""
        if self._path_provider is None:
            raise RuntimeError("Container not built. Call build() first.")
        return self._path_provider

    @property
    def virtual_container(self) -> VirtualContainer:
        """Return the virtual container."""
        if self._virtual_container is None:
            raise RuntimeError("Container not built. Call build() first.")
        return self._virtual_container

    @property
    def is_built(self) -> bool:
        """Return whether the container has been built."""
        return self._is_built

    def wire(self) -> None:
        """Connect the signals and slots of built components.

        Override it to declare an application's connections. Every component is
        built when this runs, available as the attribute it was declared under:

        ```python
        class MyApp(AppContainer):
            det_ctrl = declare_presenter(DetectorPresenter)
            img_widget = declare_view(ImageView)

            def wire(self) -> None:
                self.connect(self.det_ctrl.sig_new_data, self.img_widget.update_layers)
        ```

        Connects nothing by default.
        """

    def connect(
        self,
        signal: SignalInstance,
        slot: Callable[..., Any],
        *,
        thread: SlotThread = None,
    ) -> Connection | None:
        """Connect a signal to a slot, recording the link for teardown.

        Returns ``None`` without connecting when an end belongs to a component
        that failed to build: the link is logged at ``WARNING`` and `wire`
        continues. Any other wrong port raises.

        See [`VirtualContainer.connect`][redsun.virtual.VirtualContainer.connect].
        """
        ends: tuple[object, object] = (signal, slot)
        absent = {end.component for end in ends if isinstance(end, _NotBuilt)}
        if absent:
            named = ", ".join(repr(name) for name in sorted(absent))
            logger.warning(
                f"Not connecting {self._end_path(signal)} -> "
                f"{self._end_path(slot)}: {named} not built"
            )
            return None
        return self.virtual_container.connect(signal, slot, thread=thread)

    def _end_path(self, end: object) -> str:
        """Return one end of a connection as ``component.port``."""
        if isinstance(end, _NotBuilt):
            return str(end)
        owner = getattr(end, "__self__", None) or getattr(end, "instance", None)
        port = getattr(end, "name", None) or getattr(end, "__name__", "<anonymous>")
        return f"{self.virtual_container._label(owner)}.{port}"

    def _apply_wiring_config(self) -> None:
        """Connect the port pairs listed in the ``wiring`` configuration section.

        A rule naming a component that failed to build is logged and skipped.
        Any other wrong rule raises, including an undeclared name.
        """
        for index, rule in enumerate(self._config.get("wiring", [])):
            if not isinstance(rule, dict) or rule.keys() != {"from", "to"}:
                raise WiringError(
                    f"wiring entry {index} must be a mapping with exactly the "
                    f"keys 'from' and 'to', got {rule!r}"
                )
            try:
                self.virtual_container.connect_paths(rule["from"], rule["to"])
            except ComponentNotBuilt as e:
                if e.component not in self._failed:
                    raise
                logger.warning(
                    f"Not connecting {rule['from']} -> {rule['to']}: "
                    f"component {e.component!r} was not built"
                )

    def build(self) -> Self:
        """Build every component in dependency order.

        The order is fixed, and each step is announced as it starts:

        1. Services, through `start_services`
        2. VirtualContainer
        3. Devices
        4. Connect, every device declared with ``autoconnect`` true
        5. Presenters
        6. Views
        7. Providers, registered into the VirtualContainer
        8. Wiring, connecting the signals and slots of built components
        9. Remaining dependency injection

        A build that raises stops the services first, so no process it launched
        outlives it.
        """
        if self._is_built:
            logger.warning("Container already built, skipping rebuild")
            return self

        get_shared_loop()
        self._open_session_log()

        logger.info("Building application container...")

        # resolved even by a container that calls no hook point of its own, so
        # that a malformed hooks section is refused wherever it is built
        self._ensure_hooks()

        try:
            self._report("services")
            self.start_services()
            self._report("virtual container")
            self._create_virtual_container()
            self._report("devices")
            self._build_devices()
            self._report("connect")
            self._connect_devices()
            self._report("presenters")
            self._build_presenters()
            self._report("views")
            self._build_views()
            self._report("providers")
            self._register_providers()
            self._report("wiring")
            self._apply_wiring()
            self._report("injection")
            self._inject_dependencies()
        except BaseException:
            self._close_catalog()
            self._stop_services()
            raise

        self._is_built = True
        summary = self._summarise_build()
        if self._failed:
            logger.warning(summary)
        else:
            logger.info(summary)

        return self

    def _summarise_build(self) -> str:
        """Return what the build made, counted against what was declared.

        One line if nothing was missed; otherwise further lines name what was
        not made.
        """
        declared: tuple[tuple[str, Mapping[str, _ComponentBase[Any]]], ...] = (
            ("device", self._device_components),
            ("presenter", self._presenter_components),
            ("view", self._view_components),
        )
        counts = ", ".join(
            f"{len(self._built_of(components))}/{len(components)} {kind}s"
            for kind, components in declared
        )
        summary = f"Container built: {counts}"
        if self._failed:
            kind_of = {
                name: kind for kind, components in declared for name in components
            }
            missing = ", ".join(
                f"{name} ({kind_of.get(name, 'component')}"
                f"{', not connected' if isinstance(error, ConnectionError) else ''})"
                for name, error in self._failed.items()
            )
            summary = f"{summary}\nNot built: {missing}"
        # a service no device names is not unused: nothing was meant to use it
        named = {c.service for c in self._device_components.values()}
        used = {c.service for c in self._built if isinstance(c, _DeviceComponent)}
        unused = [
            f"{name} (no device built)"
            for name in self._services
            if name in named - used and name not in self._failed_services
        ]
        if unused:
            summary = f"{summary}\nUnused: {', '.join(unused)}"
        return summary

    def start_services(self) -> None:
        """Start every service the container launches, and attach to the rest.

        `build` calls this too. Only the first call until `shutdown` does
        anything. A service that fails to start is logged, and the build skips
        every device naming it; the rest of the session runs.
        """
        if self._services_started:
            return
        self._services_started = True
        if not self._services:
            return
        for name, service in self._services.items():
            try:
                service.start()
            except Exception as e:  # noqa: BLE001 - a missing service must not abort the app
                self._failed_services[name] = e
                logger.error(f"Failed to start service '{name}': {e}")
        summary = (
            f"Services started: {len(self._services) - len(self._failed_services)}"
            f"/{len(self._services)}"
        )
        if not self._failed_services:
            logger.info(summary)
            return
        failed = ", ".join(
            f"{name} ({reason})" for name, reason in self._failed_services.items()
        )
        logger.warning(f"{summary}\nNot started: {failed}")

    def _ensure_hooks(self) -> dict[str, object]:
        """Return the hook providers by hook point, resolved once per build.

        A subclass calling its own hook points uses this, so every hook point
        of a build uses one set of providers.
        """
        if self._hooks is None:
            self._hook_by_moment = self._resolve_hook_providers()
            self._hooks = distinct(
                self._hook_by_moment[moment]
                for moment in self._hook_keys
                if moment in self._hook_by_moment
            )
        return self._hook_by_moment

    def _resolve_hook_providers(self) -> dict[str, object]:
        """Merge the providers declared on the class with the configured ones.

        Raises
        ------
        HookError
            If an entry does not resolve, a hook point is named on both the
            class and the configuration, or a configured provider does not
            implement its point's protocol.
        """
        declared = dict(type(self)._hook_providers)
        configured = resolve_hooks(
            parse_hook_specs(
                self._config.get("hooks", {}), self._hook_keys, type(self).__name__
            )
        )
        both = sorted(declared.keys() & configured.keys())
        if both:
            named = ", ".join(repr(moment) for moment in both)
            raise HookError(
                f"hook point(s) {named} are named both on {type(self).__name__} "
                "and in the configuration; a hook point takes one provider, so "
                "drop one of the two"
            )
        for moment, hook in configured.items():
            protocol = self._hook_keys[moment]
            if not isinstance(hook, protocol):
                raise HookError(
                    f"hook provider {type(hook).__name__!r} configured at "
                    f"{moment!r} does not implement {protocol.__name__}"
                )
        return {**declared, **configured}

    def _shutdown_hooks(self) -> None:
        """Undo what the hook providers did, in reverse installation order."""
        for hook in reversed(self._hooks or ()):
            if isinstance(hook, HasShutdown):
                try:
                    hook.shutdown()
                except Exception as e:  # noqa: BLE001 - one failure must not block the rest
                    logger.error(
                        f"Error shutting down hook '{type(hook).__name__}': {e}"
                    )
        self._hooks = None
        self._hook_by_moment = {}

    def _create_virtual_container(self) -> None:
        """Create the VirtualContainer with the session configuration."""
        self._virtual_container = VirtualContainer()

        base_cfg: RedSunConfig = {
            "schema_version": self._config.get("schema_version", 1.0),
            "session": self._config.get("session", "Redsun"),
            "frontend": self._config.get("frontend", "pyqt"),
        }
        self._virtual_container._set_configuration(base_cfg)

        # parsed before the extra is checked, so a malformed section is refused
        # whether or not it is installed
        storage = StorageConfig.from_mapping(self._config.get("storage"))
        self._path_provider = SessionPathProvider(
            base_dir=storage.base_dir,
            session=base_cfg["session"],
            max_digits=storage.max_digits,
        )
        # the log opened at construction, before the root was known
        self._move_session_log(self._path_provider.base_dir)
        self._path_provider.sig_base_dir_changed.connect(self._move_session_log)
        if storage.catalog is not None:
            _require_tiled()
            self._catalog = self._start_catalog(storage.catalog)
        logger.debug("VirtualContainer created")

    def _start_catalog(self, config: CatalogConfig) -> SimpleTiledServer | None:
        """Start the session's catalog, or log why it could not.

        It reads from the session's directory and every one *config* adds,
        serves OME-Zarr images with their axis names, and has a ``TiledWriter``
        in this process store them as their store holds them.
        """
        # imported here: the tiled extra is optional, and _require_tiled has
        # already refused a session asking for a catalog without it
        from ome_tiled import OME_ZARR_MIMETYPE, OmeZarrAdapter
        from ome_tiled.bluesky import register_consolidator
        from tiled.server.simple import SimpleTiledServer

        session_dir = self.path_provider.session_dir
        server: SimpleTiledServer | None = None
        try:
            server = SimpleTiledServer(
                directory=session_dir / "catalog",
                readable_storage=[session_dir, *config.readable],
            )
            # TODO: let storage.catalog choose the adapters and consolidators
            # installed here, rather than always installing ome-tiled's

            # SimpleTiledServer takes no adapters; the first map holds the
            # catalog's own, ahead of tiled's defaults
            server.catalog.context.adapters_by_mimetype.maps[0][OME_ZARR_MIMETYPE] = (
                OmeZarrAdapter
            )
            register_consolidator()
            self.path_provider.lock_base_dir(
                "the session's catalog reads files only from the readable "
                "directories it started with; choose the root with "
                "storage.base_dir before the session starts"
            )
            return server
        except Exception as e:  # noqa: BLE001 - a catalog that fails must not abort the app
            # a server that started and then failed to be set up is stopped,
            # since nothing else holds it
            if server is not None:
                server.close()
            # a dotted key: no declared component can have this name
            self._failed["storage.catalog"] = e
            logger.error(f"Failed to start the catalog: {e}")
            return None

    def _build_devices(self) -> None:
        """Build every declared device, skipping those that fail."""
        built_devices: dict[str, Device] = {}
        for name, device_comp in self._device_components.items():
            try:
                built_devices[name] = self._built[device_comp] = device_comp.build(
                    self._prefix_for(device_comp), self.path_provider
                )
                logger.debug(f"Device '{name}' built")
            except Exception as e:  # noqa: BLE001 - a missing device must not abort the app
                self._failed[name] = e
                logger.error(f"Failed to build device '{name}': {e}")
        self._built_devices = built_devices

    def _connect_devices(self) -> None:
        """Connect every built device declared with autoconnect, all at once.

        A device not connected within `CONNECT_TIMEOUT` is recorded as failed
        and dropped, like one failing to build, so no presenter gets a device
        that raises on its first read.
        """
        targets = {
            name: device
            for name, device in self._built_devices.items()
            if self._device_components[name].autoconnect
        }
        if not targets:
            return

        async def connect_all() -> list[BaseException | None]:
            return await asyncio.gather(
                *(
                    device.connect(timeout=CONNECT_TIMEOUT)
                    for device in targets.values()
                ),
                return_exceptions=True,
            )

        for name, result in zip(targets, run_coro(connect_all()), strict=True):
            if result is None:
                continue
            component = self._device_components[name]
            reason = self._connection_failure(component, result)
            self._failed[name] = ConnectionError(reason)
            del self._built[component]
            del self._built_devices[name]
            logger.error(f"Failed to connect device '{name}': {reason}")

    def _connection_failure(
        self, device: _DeviceComponent, error: BaseException
    ) -> str:
        """Return why *device* did not connect, naming its service."""
        # ophyd-async pads a NotConnectedError's message with whitespace
        detail = str(error).strip()
        service = self._services.get(device.service or "")
        if service is None:
            return detail
        how = "launched" if service.launched else "attached"
        return (
            f"service {service.name!r} ({how}) did not answer within "
            f"{CONNECT_TIMEOUT:g} s: {detail}"
        )

    def _prefix_for(self, device: _DeviceComponent) -> str | None:
        """Return the prefix *device*'s service gives it, or ``None`` if it names none.

        Raises
        ------
        LookupError
            If the device names a service that is not declared.
        RuntimeError
            If the device names a service that did not start.
        ValueError
            If the device names a service that gives no prefix.
        """
        if device.service is None:
            return None
        if device.service not in self._services:
            raise LookupError(f"service {device.service!r} is not declared")
        if device.service in self._failed_services:
            raise RuntimeError(f"service {device.service!r} was not started")
        prefix = self._services[device.service].prefix
        if not prefix:
            raise ValueError(f"service {device.service!r} gives no prefix")
        return prefix

    def _build_presenters(self) -> None:
        """Build every declared presenter against the built devices.

        A presenter that fails is skipped, like a failed device.
        """
        for comp_name, presenter_component in self._presenter_components.items():
            try:
                self._built[presenter_component] = presenter_component.build(
                    self._built_devices
                )
            except Exception as e:  # noqa: BLE001 - a missing presenter must not abort the app
                self._failed[comp_name] = e
                logger.error(f"Failed to build presenter '{comp_name}': {e}")

    def _build_views(self) -> None:
        """Build every declared view, skipping those that fail."""
        for comp_name, view_component in self._view_components.items():
            try:
                self._built[view_component] = view_component.build()
            except Exception as e:  # noqa: BLE001 - a missing view must not abort the app
                self._failed[comp_name] = e
                logger.error(f"Failed to build view '{comp_name}': {e}")

    def _register_providers(self) -> None:
        """Bind the session's path provider and catalog address, then each component's own."""
        self.virtual_container.provide(PATH_PROVIDER, self.path_provider)
        if self._catalog is not None:
            self.virtual_container.provide(CATALOG, CatalogAddress(self._catalog.uri))
        for name, instance in self._built_of(self._components).items():
            if isinstance(instance, IsProvider):
                try:
                    instance.register_providers(self.virtual_container)
                except Exception as e:  # noqa: BLE001 - one component must not abort the app
                    self._drop(name, "register the providers of", e)

    def _drop(self, name: str, step: str, error: Exception) -> None:
        """Forget a built component whose *step* failed, and log why.

        What it was meant to publish or receive is missing for the rest of
        the session; the components relying on it fail in turn, each logged
        under its own name.
        """
        self._failed[name] = error
        del self._built[self._components[name]]
        logger.error(f"Failed to {step} '{name}': {error}")

    def _apply_wiring(self) -> None:
        """Publish the built components by name, then connect them.

        Names come first, since `wire` and the ``wiring`` section resolve
        components by name. The session's path provider is published beside
        them as ``path_provider``, so a configuration file can feed it the
        plan name.
        """
        components = self._built_of(self._components)
        if PATH_PROVIDER_PORT in components:
            raise WiringError(
                f"component {PATH_PROVIDER_PORT!r} shadows the session path "
                "provider, which is published under that name; rename it"
            )
        self.virtual_container._set_components(
            {**components, PATH_PROVIDER_PORT: self.path_provider}
        )
        self.wire()
        self._apply_wiring_config()

    def _inject_dependencies(self) -> None:
        """Let each component taking dependencies receive them."""
        for name, instance in self._built_of(self._components).items():
            if isinstance(instance, IsInjectable):
                try:
                    instance.inject_dependencies(self.virtual_container)
                except Exception as e:  # noqa: BLE001 - one component must not abort the app
                    self._drop(name, "inject dependencies into", e)

    def connect_devices(self, mock: bool = False) -> None:
        """Connect every device through ``ophyd-async``.

        Call after [`build`][redsun.containers.container.AppContainer.build],
        which already connected the devices declared with ``autoconnect``. This
        connects every device regardless, and a connected device returns at
        once. ``mock=True`` skips the hardware, for tests.

        Parameters
        ----------
        mock : bool
            Connect to mock backends, needing no hardware.

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

    def shutdown(self) -> None:
        """Undo the build, one phase at a time.

        The phases run in this order, each a method a subclass may override:

        1. ``_disconnect`` - undo the wiring.
        2. ``_shutdown_presenters`` - shut every presenter down.
        3. ``_close_catalog`` - stop the session's catalog.
        4. ``_shutdown_hooks`` - undo what the hook providers installed.
        5. ``_release_components`` - drop every built component.
        6. ``_destroy`` - end what dropping a reference does not end.

        Afterwards the container holds nothing it built, so ``devices``,
        ``presenters`` and ``views`` raise until the next ``build()``.

        Built or not, the container then stops its launched services, the last
        declared first, and closes the session's log file; the next ``build()``
        starts both again.
        """
        if self._is_built:
            self._disconnect()
            self._shutdown_presenters()
            # after the presenters, which may still be writing to it
            self._close_catalog()
            # after the components, which may still be using what a hook installed
            self._shutdown_hooks()
            self._destroy(self._release_components())

            self._is_built = False
            logger.info("Container shutdown complete")
        # started before the build, so stopped whether or not it completed, and
        # before the log file closes, since stopping logs how each service ended
        self._stop_services()
        self._close_session_log()

    def _stop_services(self) -> None:
        """Stop every service the container launched, the last declared first.

        A service failing to stop does not keep the others running. If any
        stopped, the process's Channel Access channels are closed, so a rebuilt
        container connects afresh.
        """
        stopped = False
        for name, service in reversed(self._services.items()):
            stopped = stopped or service.running
            try:
                service.stop()
            except Exception as e:  # noqa: BLE001 - one failed stop must not block the rest
                logger.error(f"Error stopping service '{name}': {e}")
        self._failed_services.clear()
        self._services_started = False
        if stopped:
            run_coro(TRANSPORTS[self.transport].release())

    def _open_session_log(self) -> None:
        """Start writing this run's records to the session's log files.

        Application records go to one file and each launched service's to its
        own, so a noisy service rotates only its own file.
        """
        if self._session_log is not None:
            return
        session = self._config["session"]
        self._session_log = SessionFileHandler(session)
        add_handler(self._session_log)
        for name, service in self._services.items():
            if service.launched:
                handler = SessionFileHandler(session, name, self._session_log.run)
                add_handler(handler, name)
                self._service_logs[name] = handler

    def _move_session_log(self, root: Path) -> None:
        """Carry this run's log files under *root*, the session's new root."""
        for handler in (self._session_log, *self._service_logs.values()):
            if handler is not None:
                handler.move(root)

    def _close_session_log(self) -> None:
        """Stop writing to the session's log files, and close them."""
        for name, handler in self._service_logs.items():
            remove_handler(handler, name)
            handler.close()
        self._service_logs.clear()
        if self._session_log is not None:
            remove_handler(self._session_log)
            self._session_log.close()
            self._session_log = None

    def _disconnect(self) -> None:
        """Undo every connection and subscription the wiring made."""
        if self._virtual_container is not None:
            self._virtual_container.disconnect_all()

    def _shutdown_presenters(self) -> None:
        """Shut down every presenter implementing ``HasShutdown``.

        A presenter failing to shut down does not stop the others.
        """
        for name, presenter in self._built_of(self._presenter_components).items():
            if isinstance(presenter, HasShutdown):
                try:
                    presenter.shutdown()
                except Exception as e:  # noqa: BLE001 - one failed shutdown must not block the rest
                    logger.error(f"Error shutting down presenter '{name}': {e}")

    def _close_catalog(self) -> None:
        """Stop the session's catalog, if one was started."""
        if self._catalog is None:
            return
        try:
            self._catalog.close()
        except Exception as e:  # noqa: BLE001 - a failed close must not block the shutdown
            logger.error(f"Error closing the catalog: {e}")
        self._catalog = None

    def _release_components(self) -> Sequence[object]:
        """Drop every built component, and return what was dropped.

        The virtual container forgets them too, so nothing the framework owns
        still references them.
        """
        if self._virtual_container is not None:
            self._virtual_container._clear_components()
        released = list(self._built.values())
        self._built.clear()
        self._failed.clear()
        self._built_devices = {}
        return released

    def _destroy(self, components: Sequence[object]) -> None:
        """Destroy the components the container has just released.

        A container bound to no toolkit can only drop the last reference, which
        does not end objects a toolkit owns outside Python. Such a toolkit
        overrides this to end them.

        *components* are already released: neither this container nor the
        virtual container holds them.
        """

    def run(self) -> None:
        """Build the container if needed, then start the application."""
        if not self._is_built:
            self.build()

        frontend = self._config.get("frontend", "pyqt")
        logger.info(f"Starting application with frontend: {frontend}")

    @classmethod
    def from_config(
        cls, config_path: str, *, log_level: int | str | None = None
    ) -> AppContainer:
        """Build a container from a YAML configuration file.

        *log_level* is passed to the container it builds.
        """
        config, plugin_types, services = load_configuration(config_path)

        namespace: dict[str, Any] = {
            name: _ServiceComponent(name, **kwargs) for name, kwargs in services.items()
        }

        named = transport_of(config)
        if named is not None:
            namespace[TRANSPORT_KEY] = checked_transport(
                named, f"the services section of {config_path}"
            )

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
                    if k not in PLUGIN_META_KEYS
                }
                namespace[name] = component(plugin_class, name, **cfg_kwargs)

        frontend = config.get("frontend", "pyqt")
        base_class = _resolve_frontend_container(frontend)

        DynamicApp: type[AppContainer] = type("DynamicApp", (base_class,), namespace)

        instance = DynamicApp(
            session=config.get("session", "Redsun"),
            frontend=frontend,
            log_level=log_level,
        )
        if "storage" in config:
            instance._config["storage"] = config["storage"]
        if "wiring" in config:
            instance._config["wiring"] = config["wiring"]
        if "hooks" in config:
            instance._config["hooks"] = config["hooks"]

        return instance


__all__ = ["AppContainer", "Frontend"]
