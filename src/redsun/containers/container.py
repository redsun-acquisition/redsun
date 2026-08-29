"""Application container for MVP architecture.

Provides `AppContainer` for declarative component registration
and dependency-ordered instantiation.
"""

from __future__ import annotations

import asyncio
import logging

# resolved at runtime: the ClassVar annotation below is evaluated by ruff's
# runtime-evaluated rules and by anything calling get_type_hints on a subclass
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
from redsun.containers._hooks import (
    HookError,
    distinct,
    known_points,
    parse_hook_specs,
    resolve_hooks,
)
from redsun.containers.components import (
    _ComponentField,
    _DeviceComponent,
    _DeviceField,
    _HookField,
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
    from collections.abc import Callable, Mapping, Sequence
    from typing import Self, TypeAlias

    from psygnal import SignalInstance

    from redsun.containers.components import _ComponentBase
    from redsun.virtual import RedSunConfig
    from redsun.virtual._wiring import SlotThread

    _ComponentFactory: TypeAlias = Callable[..., _ComponentBase[Any]]

ManifestItems = dict[str, Any]
PluginType = type[Device] | type[PPresenter] | type[PView]
PLUGIN_GROUPS = Literal["devices", "presenters", "views"]


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


def _silent(step: str) -> None:
    """Take a build step's name and do nothing with it.

    What `AppContainer` reports progress to when no hook asked for it, so the
    build has one path whether or not anything is watching.
    """


_COMPONENT_SECTIONS: frozenset[str] = frozenset({"devices", "presenters", "views"})
"""The configuration sections whose entries are a component's constructor call."""

_IDENTITY_KEYS: tuple[str, ...] = ("schema_version", "frontend")
"""Keys naming what kind of session this is, which every layered file must agree on.

Everything else describes the session's content, where a later file legitimately
overrides an earlier one.
"""

_FRONTEND_CONTAINERS: dict[str, str] = {
    "pyqt": "redsun.containers.qt._container.QtAppContainer",
    "pyside": "redsun.containers.qt._container.QtAppContainer",
}


def _read_yaml(path: Path) -> dict[str, Any]:
    """Read one YAML file into a mapping, without validating what it carries."""
    with open(path) as fh:
        data = yaml.safe_load(fh)
    if not isinstance(data, dict):
        raise TypeError(
            f"Expected a YAML mapping at top level in {path}, got {type(data).__name__}"
        )
    return data


def merge_config(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Return *base* with *overlay* laid over it, merging nested mappings.

    A key present in both is taken from *overlay* unless both values are
    mappings, which merge in turn. Anything that is not a mapping - a list, a
    scalar - is replaced rather than combined.

    A component entry is the exception: under ``devices``, ``presenters`` and
    ``views`` the section merges by component name, but a component *named* in
    *overlay* is taken from it whole. Those entries are the keyword arguments
    of a constructor call rather than a tree of settings, so one file owns one
    component's arguments and a reader stops at the last file naming it.
    """
    merged = dict(base)
    for key, value in overlay.items():
        current = merged.get(key)
        if not (isinstance(current, dict) and isinstance(value, dict)):
            merged[key] = value
        elif key in _COMPONENT_SECTIONS:
            for shadowed in current.keys() & value.keys():
                logger.debug(
                    f"Component '{shadowed}' in '{key}' is taken from a later "
                    f"configuration file, replacing the entry under it"
                )
            merged[key] = {**current, **value}
        else:
            merged[key] = merge_config(current, value)
    return merged


def _refuse_identity_conflict(
    data: dict[str, Any], overlay: dict[str, Any], path: Path
) -> None:
    """Refuse a file that contradicts what an earlier one said the session is.

    Raises
    ------
    ValueError
        If *overlay* gives a different value for a key naming the session's
        identity rather than its content.
    """
    for key in _IDENTITY_KEYS:
        if key in data and key in overlay and data[key] != overlay[key]:
            raise ValueError(
                f"Configuration file {path} sets {key}={overlay[key]!r}, "
                f"which contradicts {data[key]!r} from a file layered under it. "
                f"{key} names what kind of session this is, so every file must "
                f"agree on it."
            )


def _load_yaml(paths: Sequence[Path]) -> dict[str, Any]:
    """Read *paths* in order, lay each over the last, and validate the result.

    Required keys are checked against the merged mapping rather than against
    each file, so a file layered under another may carry a fragment.

    Raises
    ------
    ValueError
        If two files disagree about the session's schema version or frontend.
    KeyError
        If the merged mapping is missing a key `AppConfig` requires.
    """
    if len(paths) > 1:
        logger.debug(
            f"Reading configuration from {len(paths)} files, in order: "
            f"{', '.join(str(path) for path in paths)}"
        )
    data: dict[str, Any] = {}
    for path in paths:
        overlay = _read_yaml(path)
        _refuse_identity_conflict(data, overlay, path)
        data = merge_config(data, overlay)
    missing = AppConfig.__required_keys__ - data.keys()
    if missing:
        named = ", ".join(str(path) for path in paths)
        raise KeyError(
            f"Configuration ({named}) is missing required keys: "
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
        "_components",
        "_config",
        "_devices_connected",
        "_hook_by_moment",
        "_hooks",
        "_is_built",
        "_report",
        "_virtual_container",
    )

    _device_components: ClassVar[dict[str, _DeviceComponent]] = {}
    _presenter_components: ClassVar[dict[str, _PresenterComponent]] = {}
    _view_components: ClassVar[dict[str, _ViewComponent]] = {}
    _component_fields: ClassVar[dict[str, _ComponentField]] = {}
    """Every ``declare_*`` field this container and its bases declared.

    Kept past class creation so that a subclass naming its own ``config`` file
    resolves the fields it inherited against that file rather than the one its
    base was written with.
    """

    _config_paths: ClassVar[tuple[Path, ...]] = ()
    """The configuration files this container reads, in the order they layer.

    A subclass naming its own ``config`` appends to what its bases named rather
    than replacing it, so a file common to several sessions sits under the one
    that is particular to each.
    """

    BUILD_STEPS: ClassVar[tuple[str, ...]] = (
        "virtual container",
        "devices",
        "presenters",
        "views",
        "providers",
        "wiring",
        "injection",
    )
    """The steps `build` announces, in the order it reaches them.

    Each is reported as it starts, so a progress display sizes itself from the
    length of this rather than from a number of its own that would drift as the
    sequence changes.
    """

    _hook_keys: ClassVar[Mapping[str, type]] = {}
    """The hook points this container calls, in the order it reaches them.

    A key is the method the point calls, and is what names the point in a
    container class body and in the ``hooks`` section. Empty here: every moment
    a hook can act at belongs to a toolkit, so it is the container for that
    toolkit that declares one.
    """

    _hook_providers: ClassVar[dict[str, object]] = {}
    """The providers declared on this container class, by hook point.

    Built as the class is created, so that an instance declared at two points
    is one provider serving both. A subclass inherits what its bases declare.
    """

    def __init_subclass__(
        cls,
        config: str | Path | Sequence[str | Path] | None = None,
        **kwargs: Any,
    ) -> None:
        """Collect component wrappers from class attributes.

        Parameters
        ----------
        config : str | Path | Sequence[str | Path] | None
            YAML configuration file for component kwargs, or several to layer
            in order. They are read after the ones this container's bases name,
            so a later file wins a key it shares with an earlier one.
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
                config_data = _load_yaml(cls._config_paths)

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
            provider = cls._build_hook_provider(attr_name, hook_field)
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

    def __init__(self, *, session: str = "Redsun", frontend: str = "pyqt") -> None:
        self._refuse_unresolved_fields()
        self._config: AppConfig = {
            "schema_version": 1.0,
            "session": session,
            "frontend": frontend,
        }
        self._virtual_container: VirtualContainer | None = None
        self._hooks: tuple[object, ...] | None = None
        self._hook_by_moment: dict[str, object] = {}
        self._is_built: bool = False
        self._built_devices: dict[str, Device] = {}
        self._devices_connected: bool = False
        self._components: dict[str, _PresenterComponent | _ViewComponent] = {
            **self._presenter_components,
            **self._view_components,
        }
        self._report: Callable[[str], None] = _silent

        # In the declarative subclass path (class MyApp(QtAppContainer, config=...))
        # the metaclass loads the YAML only to resolve component kwargs and never
        # populates _config with top-level sections such as 'storage', 'session',
        # or 'schema_version'.  We read those here so that build() sees the same
        # state as the from_config() path, which sets them explicitly.
        config_paths: tuple[Path, ...] = getattr(type(self), "_config_paths", ())
        if config_paths:
            try:
                yaml_data = _load_yaml(config_paths)
            except Exception as e:  # noqa: BLE001 - unreadable config falls back to defaults
                named = ", ".join(str(path) for path in config_paths)
                logger.warning(f"Could not read config file(s) {named}: {e}")
                yaml_data = {}
            for key, value in yaml_data.items():
                if key not in _COMPONENT_SECTIONS:
                    self._config[key] = value  # type: ignore[literal-required]

    @classmethod
    def _refuse_unresolved_fields(cls) -> None:
        """Refuse a container whose ``from_config`` fields have no file to read.

        Deferred to construction rather than class creation: a base class exists
        to be subclassed, and the subclass is where ``config`` is named.

        Raises
        ------
        TypeError
            Naming every field that asked for a configuration section.
        """
        if cls._config_paths:
            return
        unresolved = sorted(
            attr_name
            for attr_name, field in cls._component_fields.items()
            if field.from_config is not None
        )
        if unresolved:
            raise TypeError(
                f"Component field(s) {', '.join(unresolved)} in {cls.__name__} have "
                f"from_config set but no config path was provided to the container "
                f"class"
            )

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

        The order is fixed, and each step is announced to whatever is watching
        the build:

        1. VirtualContainer
        2. Devices
        3. Presenters
        4. Views
        5. Providers, registered into the VirtualContainer
        6. Wiring, connecting the signals and slots of built components
        7. Remaining dependency injection
        """
        if self._is_built:
            logger.warning("Container already built, skipping rebuild")
            return self

        # ensure the background loop
        # is running
        _ = _loop_factory()

        logger.info("Building application container...")

        # resolved even by a container that calls no hook point of its own, so
        # that a malformed hooks section is refused wherever it is built
        self._ensure_hooks()

        self._report("virtual container")
        self._create_virtual_container()
        self._report("devices")
        self._build_devices()
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

        self._is_built = True
        logger.info(
            f"Container built: "
            f"{len(self._device_components)} devices, "
            f"{len(self._presenter_components)} presenters, "
            f"{len(self._view_components)} views"
        )

        return self

    @classmethod
    def _build_hook_provider(cls, moment: str, field: _HookField) -> object:
        """Construct the provider this container class declares at *moment*.

        Raises
        ------
        HookError
            If *moment* is not a hook point this container calls, the provider
            class rejects the keys given, or the provider does not implement
            the protocol the point calls.
        """
        if moment not in cls._hook_keys:
            raise HookError(
                f"{cls.__name__} declares a hook at {moment!r}, which is not a "
                f"hook point it calls; {known_points(cls._hook_keys)}"
            )
        declared = field.provider
        if isinstance(declared, type):
            try:
                provider: object = declared(**field.kwargs)
            except TypeError as e:
                raise HookError(
                    f"cannot construct hook provider {declared.__name__!r} "
                    f"declared at {moment!r} with {sorted(field.kwargs)}: {e}"
                ) from e
        else:
            provider = declared
        protocol = cls._hook_keys[moment]
        if not isinstance(provider, protocol):
            raise HookError(
                f"hook provider {type(provider).__name__!r} declared at "
                f"{moment!r} does not implement {protocol.__name__}"
            )
        return provider

    def _ensure_hooks(self) -> dict[str, object]:
        """Return the hook providers by hook point, resolving once per build.

        A subclass firing its own hook points calls this rather than resolving
        again, so that every hook point of one build acts on one set of
        providers.
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
            If an entry does not resolve, a hook point is named on the class
            and in the configuration, or a configured provider does not
            implement the protocol its hook point calls.
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
        """Undo what the hook providers did, in reverse order of installation."""
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
        """Create the VirtualContainer and hand it the session configuration."""
        self._virtual_container = VirtualContainer()

        base_cfg: RedSunConfig = {
            "schema_version": self._config.get("schema_version", 1.0),
            "session": self._config.get("session", "Redsun"),
            "frontend": self._config.get("frontend", "pyqt"),
        }
        self._virtual_container._set_configuration(base_cfg)
        logger.debug("VirtualContainer created")

    def _build_devices(self) -> None:
        """Build every declared device, skipping the ones that fail."""
        built_devices: dict[str, Device] = {}
        for name, device_comp in self._device_components.items():
            try:
                built_devices[name] = device_comp.build()
                logger.debug(f"Device '{name}' built")
            except Exception as e:  # noqa: BLE001 - a missing device must not abort the app
                logger.error(f"Failed to build device '{name}': {e}")
        self._built_devices = built_devices

    def _build_presenters(self) -> None:
        """Build every declared presenter against the built devices."""
        for comp_name, presenter_component in self._presenter_components.items():
            try:
                presenter_component.build(self._built_devices)
            except Exception as e:
                logger.error(f"Failed to build presenter '{comp_name}': {e}")
                raise

    def _build_views(self) -> None:
        """Build every declared view."""
        for comp_name, view_component in self._view_components.items():
            try:
                view_component.build()
            except Exception as e:
                logger.error(f"Failed to build view '{comp_name}': {e}")
                raise

    def _register_providers(self) -> None:
        """Let every component providing dependencies register them."""
        for component in self._components.values():
            if isinstance(component.instance, IsProvider):
                component.instance.register_providers(self.virtual_container)

    def _apply_wiring(self) -> None:
        """Publish the built components by name, then connect them.

        The names reach the VirtualContainer first because both `wire` and the
        ``wiring`` configuration section resolve components by name.
        """
        self.virtual_container._set_components(
            {name: comp.instance for name, comp in self._components.items()}
        )
        self.wire()
        self._apply_wiring_config()

    def _inject_dependencies(self) -> None:
        """Let every component taking dependencies receive them."""
        for component in self._components.values():
            if isinstance(component.instance, IsInjectable):
                component.instance.inject_dependencies(self.virtual_container)

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
        """Shutdown all presenters and hooks that implement ``HasShutdown``."""
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

        # after the components, which may still be using what a hook installed
        self._shutdown_hooks()

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
        if "hooks" in config:
            instance._config["hooks"] = config["hooks"]

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
