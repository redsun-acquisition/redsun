from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack, nullcontext
from copy import deepcopy
from importlib import import_module
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Final,
    Literal,
    Self,
    TypeAlias,
    TypeVar,
    cast,
    overload,
)

import yaml
from event_model import DocumentRouter
from in_n_out import Store
from ophyd_async.core import Device  # noqa: TC002
from psygnal import SignalInstance

from redsun.aio import run_coro
from redsun.catalog import CatalogAddress
from redsun.experimental.injection import (
    constant,
    register_shared,
    rejected,
    satisfying,
    shared_keys,
)
from redsun.experimental.ports import (
    SLOT_ATTR,
    SLOT_THREAD_ATTR,
    ComponentNotBuilt,
    Connection,
    Slot,
    Subscription,
    Unconnected,
    WiringError,
    owner_of,
    port_name,
    ports,
)
from redsun.experimental.registry import (
    CallbackType,
    DeviceMapping,
    SessionConfig,
)
from redsun.path_provider import PATH_PROVIDER_PORT, SessionPathProvider

from ... import _structural
from ..._catalog import require_tiled, start_catalog
from ..._config import Source, StorageConfig, as_sources, load
from ..._hooks import HookError, parse_hook_specs, resolve_hooks
from ...services._transports import (
    CHANNEL_ACCESS,
    TRANSPORT_KEY,
    TRANSPORTS,
    checked_transport,
    transport_of,
)
from .._settings import Settings
from ._declarations import (
    Declaration,
    HookDeclaration,
    Layer,
    read,
    read_hooks,
    read_services,
)
from ._factories import (
    constructor,
    device_questions,
    factory,
    get_setup_params,
    injectable,
    optional_arg,
    provider,
    setup_call,
)
from ._frontend import Frontend
from ._plugins import load_providers, manifest
from ._protocols import (
    AttachableComponent,
    BuildableSession,
    HasAsyncShutdown,
    HasSetup,
    HasShutdown,
    NamedComponent,
    Serializable,
)
from ._questions import NoAnswer, answer, shape_of

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from contextlib import AbstractContextManager

    from ophyd_async.core import SignalR
    from tiled.server.simple import SimpleTiledServer
    from typing_extensions import TypeForm

    from redsun.experimental.ports import SlotThread
    from redsun.services import Service

    from ._declarations import Key
    from ._questions import Shape

__all__ = ["BUILD_STEPS", "ConfigurationInUse", "Session"]

P = TypeVar("P")

CallbackCatalogue: TypeAlias = Mapping[str, CallbackType]
"""The key a component asks for to receive every document router the session built."""


class ConfigurationInUse(OSError):
    """Raised when a session is asked to write over a source it was built from.

    A saved file is one flat session, where a source may be shared by several
    and hand-written. Overwriting one replaces what those other sessions read.
    """

    def __init__(self, path: Path) -> None:
        super().__init__(f"{path} is a source this session was built from")
        self.path = path


logger = logging.getLogger("redsun")


def unaccepted(cls: type, entry: Mapping[str, object]) -> list[str]:
    """Return the keys of *entry* that *cls* would refuse to be built from.

    The constructor's parameters decide this, not the keys the configuration
    carried. A component serializes every parameter it has, including one
    that took its default and that no source named, and that key is correct.
    A constructor taking ``**kwargs`` accepts anything, so it refuses none.
    """
    params = constructor(cls).parameters
    if any(p.kind is p.VAR_KEYWORD for p in params.values()):
        return []
    return sorted(set(entry) - {name for name in params if name != "name"})


def silent(step: str) -> None:
    """Take a build step's name and do nothing with it.

    What a session reports progress to when no hook asked for it, so the
    build has one path whether or not anything is watching.
    """


ORDER: Final[dict[Layer, int]] = {Layer.DEVICE: 0, Layer.PRESENTER: 1, Layer.VIEW: 2}
"""The order the layers are built in, which is the order they may depend in."""

BUILD_STEPS: Final[tuple[str, ...]] = (
    "services",
    "devices",
    "connect",
    "registry",
    "presenters",
    "views",
    "setup",
    "seal",
    "wiring",
    "presentation",
    "report",
)
"""The steps a build reports, in order, to whatever is watching it.

A `during_build` hook is told one of these names as each step starts, so a
progress display that counts them needs the total in advance to show how far
along it is. `redsun.experimental` does not re-export it: it names the steps of
this session class rather than the layer's surface.

`Session.build` runs two steps before the first of these, reading the
configuration and starting the toolkit's runtime, and reports neither. A hook
covering the build is a toolkit object itself, a splash screen being the case
it was written for, so nothing can be watching until the runtime that shows it
exists.
"""

CONNECT_TIMEOUT: Final = 10.0
"""Seconds the build waits for each device it connects."""

FRONTENDS: Final[dict[str, str]] = {
    "pyqt": "redsun.experimental.session.qt:QtSession",
    "pyside": "redsun.experimental.session.qt:QtSession",
}
"""The session class a configuration's frontend name builds on."""


class Session(BuildableSession):
    """One running application, whose components are declared as annotations.

    ```python
    class MyApp(QtSession):
        config = "session.yaml"

        stage: AsDevice[MyStage]
        motor_ctrl: AsPresenter[MotorPresenter]
        motor_widget: Annotated[AsView[MotorView], Declare(step_size=5.0)]

        def wire(self) -> None:
            self.connect(self.motor_ctrl.sig_moved, self.motor_widget.update)
    ```

    An annotation is a declaration only if it names a layer, so a session may
    hold ordinary attributes alongside its components. The attribute name is
    both the component name and its configuration key; `Alias` and `FromConfig`
    override each. Reading a declared attribute on a built session gives the
    instance, typed by its annotation.

    A component that failed to build is set on nothing, so reading its name
    raises ``AttributeError`` rather than answering ``None``.
    """

    __slots__ = (
        "__dict__",
        "__weakref__",
        "_answered",
        "_baseline",
        "_built_components",
        "_callbacks",
        "_catalog",
        "_config",
        "_connections",
        "_declarations",
        "_devices",
        "_failed",
        "_failed_services",
        "_hooks",
        "_is_built",
        "_links",
        "_merged",
        "_names",
        "_not_set_up",
        "_path_provider",
        "_releases",
        "_report",
        "_services",
        "_session_config",
        "_settings",
        "_shared",
        "_shared_values",
        "_storage",
        "_store",
        "_subscription_records",
        "_subscriptions",
        "_transport",
    )

    config: ClassVar[Source | Sequence[Source] | None] = None
    """The configuration this session is declared with.

    One source or several, each a path to a YAML file or a mapping already in
    hand. Several layer in the order given, and a subclass's layer over its
    bases', so a base holds what every session of an instrument shares and a
    subclass holds what makes it that session.
    """

    providers: ClassVar[list[type]] = []
    """The shared services this session installs before any component.

    Each is an ordinary class whose methods marked with
    `redsun.experimental.provides` put values in the session for components to
    ask for by type. A provider has no name, no layer and no wiring.
    """

    hook_points: ClassVar[Mapping[str, type]] = {}
    """The points this session calls a hook at, by the protocol each demands.

    Empty here: every hook point belongs to a toolkit, so a toolkit session
    such as `redsun.experimental.session.qt.QtSession` names its own.
    """

    frontend: ClassVar[type[Frontend]] = Frontend
    """The toolkit this session is built against.

    Set by subclassing, as `redsun.experimental.session.qt.QtSession` does. The
    default attaches nothing and constrains no view.
    """

    def __init__(self, config: Source | Sequence[Source] | None = None) -> None:
        """Prepare an empty session, to be filled by `build`.

        *config* layers over whatever the class declares rather than replacing
        it, so a caller naming one key changes that key and leaves the rest.
        """
        self._config = config
        self._merged: dict[str, Any] | None = None
        self._hooks: dict[str, object] | None = None
        self._report: Callable[[str], None] = silent
        self._releases = ExitStack()
        self._declarations: dict[str, Declaration] = {}
        self._services: dict[str, Service] = {}
        self._failed_services: dict[str, BaseException] = {}
        self._transport = CHANNEL_ACCESS
        self._devices: dict[str, Device] = {}
        # what the build could not make, by component name, so that a
        # component built from one of them is skipped rather than refused
        self._failed: dict[str, BaseException] = {}
        self._answered: set[str] = set()
        self._baseline: dict[str, Mapping[str, object]] = {}
        self._session_config = SessionConfig()
        self._storage: StorageConfig | None = None
        self._path_provider: SessionPathProvider | None = None
        self._catalog: SimpleTiledServer | None = None
        self._callbacks: dict[str, CallbackType] = {}
        self._built_components: dict[str, object] = {}
        # a component whose setup could not run: kept, and named in the report
        self._not_set_up: dict[str, BaseException] = {}
        self._names: dict[int, str] = {}
        self._links: list[tuple[SignalInstance, Callable[..., Any]]] = []
        self._connections: list[Connection] = []
        # the forwarding function is held because ophyd-async releases a
        # subscription by identity: clear_sub needs the object back
        self._subscriptions: list[
            tuple[SignalR[Any], Callable[[Any], None], SignalInstance]
        ] = []
        self._subscription_records: list[Subscription] = []
        self._settings: Settings | None = None
        self._store: Store | None = None
        # the component sharing each key, carried across the layer steps so
        # that a presenter and a view offering one type still clash
        self._shared: dict[Key, str] = {}
        self._shared_values: list[tuple[str, object]] = []
        self._is_built = False

    @classmethod
    def from_config(cls, source: Source | Sequence[Source]) -> Self:
        """Return a session described entirely by *source*.

        Every component the configuration names is declared, its layer coming
        from the section it appears under, so a session needs no class
        of its own. The ``frontend`` key chooses the class to build
        on; naming none builds on this one, which is what a session with no
        toolkit wants.

        The session comes back unbuilt, so that whatever the configuration
        cannot say is still said in Python before `build` runs.

        Raises
        ------
        ValueError
            If the configuration names a frontend no session is built
            against.
        TypeError
            If it names one this session is not built against.
        """
        config = load(source)
        return cast("Self", base_for(cls, config.get("frontend"))(config))

    @property
    def services(self) -> Mapping[str, Service]:
        """The session's services, started or not."""
        return dict(self._services)

    @property
    def transport(self) -> str:
        """What the session's services speak, one for all of them.

        Named once under ``services`` in the configuration; ``channel-access``
        when it names nothing.
        """
        return self._transport

    @property
    def devices(self) -> Mapping[str, Device]:
        """The devices that built successfully."""
        return dict(self._devices)

    @property
    def presenters(self) -> Mapping[str, NamedComponent]:
        """The presenters that built successfully."""
        return self._built(Layer.PRESENTER)

    @property
    def views(self) -> Mapping[str, AttachableComponent]:
        """The views that built successfully, ready for a frontend to attach."""
        return self._built(Layer.VIEW)

    @property
    def view_arguments(self) -> Mapping[str, object]:
        """What the session passes every view's constructor, besides its name.

        Nothing here. A session bound to a toolkit passes what its views are
        built with, by keyword.
        """
        return {}

    @property
    def declarations(self) -> Mapping[str, Declaration]:
        """The declarations collected from the class."""
        return dict(self._declarations)

    @property
    def settings(self) -> Settings:
        """What this session remembers about how one user likes to run it.

        Per user and per machine rather than part of the session file, and
        registered in the store, so an action asks for it by type.

        Raises
        ------
        RuntimeError
            If read before `build`, which is where it is opened.
        """
        if self._settings is None:
            raise RuntimeError("Call build() before reading the settings")
        return self._settings

    @property
    def is_built(self) -> bool:
        """Whether `build` has completed."""
        return self._is_built

    def _sources(self) -> list[Source]:
        """Every configuration source this session layers, outermost last.

        A class contributes what its own body declares, so a subclass layers
        over its bases rather than replacing them, and the sources given to
        the constructor come last.
        """
        found: list[Source] = []
        for klass in reversed(type(self).__mro__):
            found.extend(as_sources(klass.__dict__.get("config")))
        return found + as_sources(self._config)

    def _configuration(self) -> dict[str, Any]:
        """Merge every source this session layers, reading each one once.

        The result is kept, so that a subclass needing it before the
        components are built does not read the files a second time.
        """
        if self._merged is None:
            self._merged = load(self._sources())
        return self._merged

    @property
    def hooks(self) -> Mapping[str, object]:
        """The hook provider this session installs at each point, built once.

        A subclass firing a point calls this rather than resolving again, so
        that every point of one build acts on one set of providers.

        Raises
        ------
        HookError
            If a point is claimed by more than one provider, a provider cannot
            be built, or one does not implement the protocol its point calls.
        """
        if self._hooks is None:
            self._hooks = self._resolve_hooks(self._configuration())
        return self._hooks

    def _resolve_hooks(self, config: Mapping[str, Any]) -> dict[str, object]:
        """Build the providers this class declares and the configuration names.

        Raises
        ------
        HookError
            If both name one point, a provider cannot be built, or one does
            not implement the protocol its point calls.
        """
        points = self.hook_points
        owner = type(self).__name__
        built: dict[int, object] = {}
        declared: dict[str, object] = {}
        for moment, declaration in read_hooks(type(self), points).items():
            provider = built.get(id(declaration))
            if provider is None:
                provider = instantiate(declaration, owner)
                built[id(declaration)] = provider
            declared[moment] = provider

        configured = resolve_hooks(
            parse_hook_specs(config.get("hooks", {}), points, owner)
        )
        both = sorted(declared.keys() & configured.keys())
        if both:
            named = ", ".join(repr(moment) for moment in both)
            raise HookError(
                f"hook point(s) {named} are named both on {owner} and in the "
                "configuration; a hook point takes one provider, so drop one "
                "of the two"
            )

        resolved = {**declared, **configured}
        for moment, provider in resolved.items():
            protocol = points[moment]
            if not isinstance(provider, protocol):
                raise HookError(
                    f"hook provider {type(provider).__name__!r} at {moment!r} "
                    f"does not implement {protocol.__name__}"
                )
        return resolved

    @property
    def name(self) -> str:
        """What this session is called.

        The configuration's ``name``, or this session's own class name when
        the configuration says nothing. A class name is distinct per session
        where a shared constant would not be.
        """
        declared = self._configuration().get("name")
        if isinstance(declared, str) and declared:
            return declared
        return type(self).__name__

    @property
    def storage(self) -> StorageConfig:
        """The session's storage configuration.

        Raises
        ------
        RuntimeError
            If read before `build`.
        """
        if self._storage is None:
            raise RuntimeError("Call build() before reading storage")
        return self._storage

    @property
    def path_provider(self) -> SessionPathProvider:
        """The session's path provider, shared by every device taking one.

        Raises
        ------
        RuntimeError
            If read before `build`.
        """
        if self._path_provider is None:
            raise RuntimeError("Call build() before reading path_provider")
        return self._path_provider

    def make_store(self) -> Store:
        """Return the registry this session builds its components out of.

        Named after the session and constructed rather than registered:
        ``Store.create`` would enter it in the process-wide registry, where a
        second session of one name refuses to start and an unfinished one
        keeps the name until it is destroyed. Nothing here looks a store up by
        name, so the registry buys nothing and costs a teardown obligation on
        every session that ends without one.

        A session owning an application of its own overrides this to share
        that application's store, which is what lets a command reach a
        component. That one *is* registered, by app-model, and freed by
        ``Application.destroy``.
        """
        return Store(self.name)

    def _share(self, store: Store, config: Mapping[str, Any]) -> None:
        """Build the shared services this session installs, before any component.

        A provider owns no name, no layer and no wiring. It exists to put
        values in the store, through methods marked with
        `redsun.experimental.provides`, and its own constructor is filled from
        the store like anything else.
        """
        classes: dict[str, type] = {cls.__name__: cls for cls in self.providers}
        classes.update(load_providers(config))
        for name, cls in classes.items():
            params = injectable(cls, {}, binds_name=False)
            refuse_unanswered(store, name, params)
            instance = store.inject(provider(cls, name))()
            shared = register_shared(store, instance, cls, name, self._shared)
            self._shared_values.extend((name, value) for value in shared)

    def build(self) -> Self:
        """Run each step of `BuildableSession` in turn, announcing all but two.

        Devices are built first and on their own, so that one which fails is
        logged and skipped rather than stopping the build. The components
        follow in layer order, and within a layer in the order they are built
        from one another.

        A session built against a toolkit fills `start_runtime` and
        `present` rather than overriding this method, so the order the steps
        run in is written once and a toolkit can act between two of them.
        `read_configuration` and `start_runtime` run before the span opens and
        are not announced, a hook covering the build being a toolkit object
        that cannot exist before the runtime it is shown on. A step that
        raises stops the build, which is the one failure a session does not
        carry on past, and `shutdown` gives back what the finished steps took
        before the exception leaves.
        """
        if self._is_built:
            logger.warning("Container already built, skipping rebuild")
            return self
        try:
            self.read_configuration()
            self.start_runtime()
            with self.open_span() as report:
                self._report = report
                for step, run in (
                    ("services", self.start_services),
                    ("devices", self.build_devices),
                    ("connect", self.connect_built_devices),
                    ("registry", self.open_registry),
                    ("presenters", self.build_presenters),
                    ("views", self.build_views),
                    ("setup", self.setup_components),
                    ("seal", self.seal),
                    ("wiring", self.apply_wiring),
                    ("presentation", self.present),
                    ("report", self.log_summary),
                ):
                    self._report(step)
                    run()
        except BaseException:
            self.shutdown()
            raise
        self._is_built = True
        return self

    def open_span(self) -> AbstractContextManager[Callable[[str], None]]:
        """Return the span the build announces its steps to.

        Nothing watches by default, so this is the reporter already in place
        and the build has one path whether or not a hook opened a span.
        """
        return nullcontext(self._report)

    def on_release(self, release: Callable[[], None]) -> None:
        """Register how to give something back, as the step takes it.

        Registering at the moment of taking is what lets one teardown serve a
        finished session and a build that stopped halfway: either way what
        runs is what was actually taken.
        """
        self._releases.callback(release)

    def read_configuration(self) -> None:
        """Merge the sources, install the hooks, and read the declarations."""
        manifest.cache_clear()
        config = self._configuration()
        logger.debug("Hooks installed at: %s", ", ".join(self.hooks) or "no points")
        self._set_configuration(config, self.name)
        self._declarations = read(type(self), config, self.frontend)
        for declaration in self._declarations.values():
            if declaration.refusal is not None:
                self._skip(declaration, declaration.refusal)
        # read only classes, so a mistake is reported before anything starts
        self._refuse_component_values(self._components())
        self._check_layers(self._components())
        self._transport = self._read_transport(config)
        self._services = read_services(type(self), config, self._transport)
        clash = sorted(self._services.keys() & self._declarations.keys())
        if clash:
            raise TypeError(
                f"{type(self).__qualname__} names {listed(clash)} as both a "
                "service and a component"
            )
        for name, service in self._services.items():
            setattr(self, name, service)
        self._storage = StorageConfig.from_mapping(config.get("storage"))
        if self._storage.catalog is not None:
            require_tiled()
        self._path_provider = SessionPathProvider(
            base_dir=self._storage.base_dir,
            session=self.name,
            max_digits=self._storage.max_digits,
        )

    def start_runtime(self) -> None:
        """Put in place what a component may not be constructed without.

        Nothing here: a session bound to no toolkit has no runtime of its
        own. One that is bound to a toolkit makes its objects here, before the
        first component exists and before anything can watch the build.
        """

    def open_registry(self) -> None:
        """Open the store the components are built out of, and fill it.

        The settings and the shared services come first and the questions
        the components ask are answered next, so that everything a
        constructor may reach for is registered before the first one runs.
        """
        store = self.make_store()
        self._store = store
        self._settings = Settings.for_session(self.name)
        store.register_provider(constant(self._settings), type_hint=Settings)
        self._register_framework_values(store, lambda: dict(self._devices))
        self._share(store, self._configuration())

    def seal(self) -> None:
        """Check what was built, then close the session to further building."""
        self._set_components(
            {
                declaration.name: declaration.instance
                for declaration in self._components()
                if declaration.instance is not None
            }
        )
        self._baseline = self._serialized()

    def apply_wiring(self) -> None:
        """Connect the ports the class declares, then those the file names."""
        self.wire()
        self._apply_wiring_config(self._configuration())
        self._warn_unused()

    def present(self) -> None:
        """Assemble what was built into whatever shows it.

        Nothing here: a session bound to no toolkit shows nothing, which is
        what a headless test wants. One bound to a toolkit puts its views
        where each asks to be.
        """

    def log_summary(self) -> None:
        """Log what the build made, counted against what was declared."""
        summary = self._summarise_build()
        if self._failed or self._not_set_up:
            logger.warning(summary)
        else:
            logger.info(summary)

    def _summarise_build(self) -> str:
        """Return what the build made, counted against what was declared.

        A build that missed nothing is one line; one that did names what it
        could not make on a second.
        """
        counted = []
        for layer in Layer:
            declared = [d for d in self._declarations.values() if d.kind is layer]
            built = sum(1 for d in declared if d.instance is not None)
            counted.append(f"{built}/{len(declared)} {layer}s")
        summary = f"Container built: {', '.join(counted)}"
        for label, names in (
            ("Not built", self._failed),
            ("Not set up", self._not_set_up),
        ):
            if names:
                named = ", ".join(
                    f"{name} ({self._declarations[name].kind}"
                    f"{', not connected' if isinstance(reason, ConnectionError) else ''})"
                    for name, reason in names.items()
                )
                summary += f"\n{label}: {named}"
        named_services = {d.service for d in self._declarations.values()}
        used = {
            d.service for d in self._declarations.values() if d.instance is not None
        }
        idle = named_services - used - self._failed_services.keys()
        unused = [name for name in self._services if name in idle]
        if unused:
            summary += "\nUnused: " + ", ".join(
                f"{name} (no device built)" for name in unused
            )
        return summary

    def wire(self) -> None:
        """Connect the signals and slots of built components.

        Every component exists by the time this runs. Connects nothing by
        default.
        """

    def connect_devices(self, mock: bool = False) -> None:
        """Connect every built device through ophyd-async.

        Parameters
        ----------
        mock : bool
            Connect each device to a simulated backend rather than to the
            hardware it names.

        Raises
        ------
        RuntimeError
            If called before `build`.
        """
        if not self._is_built:
            raise RuntimeError("Call build() before connect_devices()")

        async def connect_all() -> None:
            await asyncio.gather(
                *[device.connect(mock=mock) for device in self._devices.values()]
            )

        run_coro(connect_all())

    def shutdown(self) -> None:
        """Run every registered release, in the reverse of the order taken.

        Connections go first, so nothing is delivered to a component that is
        already finalizing. The releases follow: the ``shutdown`` method of
        every component that has one, then whatever a toolkit put in place.
        Calling it a second time, or on a session that was never built, runs
        nothing: a release is dropped as it runs.
        """
        self._is_built = False
        self.disconnect_all()
        self._releases.close()
        self._callbacks.clear()
        self._not_set_up.clear()
        self._built_components.clear()
        self._names.clear()
        self._shared.clear()
        logger.info("Container shutdown complete")

    def serialize(self) -> dict[str, Any]:
        """Return the configuration that would rebuild this session.

        The merged configuration, holding the entry each built component
        asked for through `redsun.experimental.Serializable`. A component
        that implements none of it, that failed to build, or that asked for a
        key its constructor would refuse keeps the entry the session was
        built from, and no other component is affected by that.

        Layered sources are merged before anything is built, so what comes
        back is one flat configuration whatever the session was built from.
        """
        config = deepcopy(self._configuration())
        for declaration in self._declarations.values():
            entry = self._entry_for(declaration)
            if entry is not None:
                if declaration.service is not None:
                    entry["service"] = declaration.service
                if not declaration.autoconnect:
                    entry["autoconnect"] = False
                section = config.setdefault(declaration.kind.section, {})
                section[declaration.name] = entry
        return config

    def write(self, path: str | Path) -> Path:
        """Write the configuration that would rebuild this session to *path*.

        One flat file whatever the session was built from, so it opens on its
        own with nothing to assemble first. Comments do not survive, the file
        being written rather than edited, and the keys come out in the order
        the merged configuration holds them.

        Raises
        ------
        ConfigurationInUse
            If *path* is a source this session was built from.
        """
        target = Path(path)
        if target.resolve() in self._source_paths():
            raise ConfigurationInUse(target)
        target.write_text(
            yaml.safe_dump(self.serialize(), sort_keys=False), encoding="utf-8"
        )
        logger.info("Wrote the configuration of '%s' to %s", self.name, target)
        return target

    def _source_paths(self) -> set[Path]:
        """Return the files this session was built from, resolved."""
        return {
            Path(source).resolve()
            for source in self._sources()
            if isinstance(source, (str, Path))
        }

    def has_changes(self) -> bool:
        """Whether any component asks to be written differently than at build.

        The session compares against what each component serialized once the
        build finished, not against the configuration it was built from.

        A value changed and changed back reads as unchanged, and a component
        that does not serialize itself never reports a change.
        """
        return self._serialized() != self._baseline

    def _serialized(self) -> dict[str, Mapping[str, object]]:
        """Return what each built component that serializes itself asks for.

        The keys are not checked against the constructor, as they are where
        `serialize` places an entry: a key that would be refused there still
        tells whether the component has changed.
        """
        found: dict[str, Mapping[str, object]] = {}
        for declaration in self._declarations.values():
            serializable = as_protocol(declaration.instance, Serializable)
            if serializable is not None:
                found[declaration.name] = serializable.serialize()
        return found

    def _entry_for(self, declaration: Declaration) -> dict[str, Any] | None:
        """Return the entry *declaration*'s component asks to be written.

        ``None`` where there is nothing to write, which leaves the entry the
        session loaded in place. One refused key discards the whole entry
        rather than only itself: dropping the key alone would leave an entry
        the component never asked for, where a renamed setting writes the new
        key, loses it, and keeps the old one beside values that assume the
        rename.
        """
        serializable = as_protocol(declaration.instance, Serializable)
        if serializable is None:
            return None
        entry = dict(serializable.serialize())
        refused = unaccepted(declaration.cls, entry)
        if not refused:
            return entry
        logger.warning(
            "'%s' tried to save %s, which %s does not accept; keeping the "
            "entry as loaded",
            declaration.name,
            ", ".join(refused),
            type(serializable).__name__,
        )
        return None

    def _register_framework_values(
        self, store: Store, devices: Callable[[], DeviceMapping]
    ) -> None:
        """Register everything the framework knows on *store*.

        Every component may ask for it by type. The callback catalogue is a
        copy, complete because it is read in `setup`, once every router exists.
        """
        store.register_provider(lambda: self._session_config, type_hint=SessionConfig)
        store.register_provider(devices, type_hint=DeviceMapping)
        store.register_provider(
            lambda: self._path_provider, type_hint=SessionPathProvider
        )
        if self._catalog is not None:
            address = CatalogAddress(self._catalog.uri)
            store.register_provider(lambda: address, type_hint=CatalogAddress)
        store.register_provider(self._catalogue, type_hint=CallbackCatalogue)

    def _catalogue(self) -> dict[str, CallbackType]:
        """Return the document routers in declaration order."""
        return {
            n: self._callbacks[n] for n in self._declarations if n in self._callbacks
        }

    def _set_configuration(self, config: Mapping[str, Any], name: str) -> None:
        """Set the session configuration, for the components to read.

        *name* is what the session is called when the configuration does not
        say, which the session takes from its own class.
        """
        self._session_config = SessionConfig(
            schema_version=config.get("schema_version", 1.0),
            frontend=config.get("frontend", "pyqt"),
            name=config.get("name", name),
            metadata=dict(config.get("metadata", {})),
        )

    @property
    def callbacks(self) -> dict[str, CallbackType]:
        """The document routers the session built, by name."""
        return dict(self._callbacks)

    def _set_components(self, components: Mapping[str, object]) -> None:
        """Record the names built components are known by.

        Both mappings are filled in place rather than rebound: a live view
        handed to a component holds the mapping itself, and rebinding would
        leave it looking at the empty one it was given during the build.
        """
        self._built_components.clear()
        self._built_components.update(components)
        self._names.clear()
        self._names.update({id(c): name for name, c in components.items()})

    def _label(self, component: object | None) -> str:
        if component is None:
            return "<unknown>"
        return self._names.get(id(component), type(component).__name__)

    def _affinity(self, slot: Callable[..., Any], thread: SlotThread) -> SlotThread:
        declaration: Slot | None = getattr(slot, SLOT_ATTR, None)
        # a marker with a thread is a slot, whichever layer's decorator set it
        if declaration is None or not hasattr(declaration, "thread"):
            name = getattr(slot, "__qualname__", repr(slot))
            raise WiringError(
                f"{name} is not connectable; mark it with the 'slot' decorator"
            )
        if thread is not None:
            return thread
        consumer = getattr(slot, "__self__", None)
        return declaration.thread or cast(
            "SlotThread", getattr(type(consumer), SLOT_THREAD_ATTR, None)
        )

    def connect(
        self,
        signal: SignalInstance,
        slot: Callable[..., Any],
        *,
        thread: SlotThread = None,
    ) -> Connection:
        """Connect a signal to a slot and record the link.

        Parameters
        ----------
        signal : SignalInstance
            The emitting signal.
        slot : Callable[..., Any]
            A bound method marked with [`slot`][redsun.virtual.slot]. May be a
            coroutine function.
        thread : SlotThread
            Delivery thread. Defaults to the affinity the slot declares, then
            to the one its class declares.

        Returns
        -------
        Connection
            The recorded link.

        Raises
        ------
        WiringError
            If *slot* is not marked as connectable, or if psygnal rejects the
            two signatures.
        """
        thread = self._affinity(slot, thread)
        link = Connection(
            publisher=self._label(owner_of(signal)),
            publisher_port=signal.name or "<anonymous>",
            consumer=self._label(getattr(slot, "__self__", None)),
            consumer_port=port_name(slot),
            thread=thread,
        )
        try:
            signal.connect(slot, thread=thread)
        except (TypeError, ValueError) as e:
            raise WiringError(f"cannot connect {link}: {e}") from e

        self._links.append((signal, slot))
        self._connections.append(link)
        logger.debug(f"Connected {link}")
        return link

    def subscribe(
        self,
        signal: SignalR[Any],
        slot: Callable[..., Any],
        *,
        thread: SlotThread = None,
    ) -> Subscription:
        """Subscribe a slot to an ophyd-async device signal and record it.

        Delivery is marshalled through a psygnal signal, so *thread* behaves as
        it does for `connect`. This is the only way a device signal can reach a
        slot with a thread affinity: ophyd-async calls its subscribers on
        whatever thread produced the reading.

        Parameters
        ----------
        signal : SignalR[Any]
            The device signal to observe.
        slot : Callable[..., Any]
            A bound method marked with [`slot`][redsun.virtual.slot], called
            with the reading dictionary.
        thread : SlotThread
            Delivery thread. Defaults to the affinity the slot declares, then
            to the one its class declares.

        Returns
        -------
        Subscription
            The recorded subscription.

        Raises
        ------
        WiringError
            If *slot* is not marked as connectable.
        """
        thread = self._affinity(slot, thread)
        relay = SignalInstance((object,), name=signal.name)
        relay.connect(slot, thread=thread)

        def forward(reading: Any) -> None:
            relay.emit(reading)

        record = Subscription(
            source=signal.name,
            consumer=self._label(getattr(slot, "__self__", None)),
            consumer_port=port_name(slot),
            thread=thread,
        )

        async def attach() -> None:
            signal.subscribe_reading(forward)

        # ophyd-async requires a running loop to subscribe, and callers run on
        # the main thread during the build
        run_coro(attach())
        self._subscriptions.append((signal, forward, relay))
        self._subscription_records.append(record)
        logger.debug(f"Subscribed {record}")
        return record

    @property
    def subscriptions(self) -> list[Subscription]:
        """The device-signal subscriptions made through this session."""
        return list(self._subscription_records)

    def connect_paths(
        self, source: str, target: str, *, thread: SlotThread = None
    ) -> Connection:
        """Connect two ports addressed as ``component.port``.

        The string form of `connect`, used by the ``wiring`` section of a
        configuration file.

        Parameters
        ----------
        source : str
            Path of the emitting signal.
        target : str
            Path of the consuming slot.
        thread : SlotThread
            Delivery thread, overriding the slot and its class.

        Returns
        -------
        Connection
            The recorded link.

        Raises
        ------
        WiringError
            If either path is malformed, names a component that was not built,
            or names a port that component does not expose.
        """
        signal = self._resolve_port(source, "signal")
        slot = self._resolve_port(target, "slot")
        return self.connect(
            cast("SignalInstance", signal),
            cast("Callable[..., Any]", slot),
            thread=thread,
        )

    def _resolve_port(self, path: str, kind: str) -> object:
        """Look up the signal or slot a ``component.port`` path names."""
        component_name, _, port = path.partition(".")
        if not component_name or not port or "." in port:
            raise WiringError(f"{path!r} is not a port path; expected 'component.port'")
        component = (
            self._path_provider
            if component_name == PATH_PROVIDER_PORT
            else self._built_components.get(component_name)
        )
        if component is None:
            known = ", ".join(sorted(self._built_components)) or "none"
            raise ComponentNotBuilt(
                component_name,
                f"{path!r} names component {component_name!r}, which was not "
                f"built. Built: {known}",
            )
        surface = ports(component)
        available = surface.signals if kind == "signal" else surface.slots
        if port not in available:
            known = ", ".join(sorted(available)) or "none"
            raise WiringError(
                f"{component_name!r} exposes no {kind} named {port!r}. "
                f"Its {kind} ports: {known}"
            )
        return available[port]

    @property
    def connections(self) -> list[Connection]:
        """The links established so far."""
        return list(self._connections)

    @property
    def unconnected(self) -> Unconnected:
        """Ports of the built components that no connection reaches.

        The complement of `connections` and `subscriptions`: what a component
        offers and nothing uses.

        Raises
        ------
        WiringError
            If a component exposes two signals under one port name.
        """
        used_signals = {(c.publisher, c.publisher_port) for c in self._connections}
        used_slots = {(c.consumer, c.consumer_port) for c in self._connections}
        used_slots |= {
            (s.consumer, s.consumer_port) for s in self._subscription_records
        }

        signals: list[str] = []
        slots: list[str] = []
        for name, component in self._built_components.items():
            surface = ports(component)
            signals += [
                f"{name}.{port}"
                for port in surface.signals
                if (name, port) not in used_signals
            ]
            slots += [
                f"{name}.{port}"
                for port in surface.slots
                if (name, port) not in used_slots
            ]
        return Unconnected(signals=signals, slots=slots)

    def satisfying(self, protocol: TypeForm[P]) -> dict[str, P]:
        """Return the built components satisfying *protocol*, by name."""
        return satisfying(self._built_components, protocol)

    def rejected(self, protocol: type) -> dict[str, list[str]]:
        """Return why each component that nearly satisfies *protocol* does not."""
        return rejected(self._built_components, protocol)

    def disconnect_all(self) -> None:
        """Undo every connection and subscription made through this session."""
        for signal, slot in self._links:
            signal.disconnect(slot, missing_ok=True)
        self._links.clear()
        self._connections.clear()

        async def release(signal: SignalR[Any], forward: Callable[[Any], None]) -> None:
            signal.clear_sub(forward)

        for device_signal, forward, relay in self._subscriptions:
            run_coro(release(device_signal, forward))
            relay.disconnect()
        self._subscriptions.clear()
        self._subscription_records.clear()

    def _components(self) -> list[Declaration]:
        return [
            d
            for d in self._declarations.values()
            if d.kind is not Layer.DEVICE and d.refusal is None
        ]

    def build_presenters(self) -> None:
        """Construct the presenter layer, in the order it depends in."""
        self._construct(Layer.PRESENTER)

    def build_views(self) -> None:
        """Construct the view layer, in the order it depends in."""
        self._construct(Layer.VIEW)

    def setup_components(self) -> None:
        """Hand every component what another component owns.

        Every presenter and view exists by now, so a `setup` may take a value
        another component shares, a census of the session, or a component
        itself. One that cannot run is reported and changes nothing else: the
        component keeps its place, its wiring and what its constructor made,
        and what its `setup` was going to assign is missing where it is used.

        Raises
        ------
        RuntimeError
            If the registry step has not opened the store yet.
        TypeError
            If a `setup` asks for something nothing in the session declares.
        """
        store = self._store
        if store is None:
            raise RuntimeError("The registry step has to run before a component is")
        components = self._components()
        built = {d.name: d.instance for d in components if d.instance is not None}
        for declaration in components:
            instance = declaration.instance
            if instance is None or not issubclass(declaration.cls, HasSetup):
                continue
            params = get_setup_params(declaration.cls)
            questions = {
                pname: shape
                for pname, hint in params.items()
                if (shape := shape_of(hint)) is not None
            }
            missing = unanswered(
                store, {p: h for p, h in params.items() if p not in questions}
            )
            if missing:
                absent = self._blamed(hint for _, hint in missing)
                if not absent:
                    raise TypeError(
                        unanswered_message(f"{declaration.name}.setup", missing)
                    )
                self._not_set_up[declaration.name] = TypeError(
                    f"{listed(sorted(absent))} was not built"
                )
            else:
                try:
                    answers = self._answers_for(declaration, questions, built)
                except NoAnswer as e:
                    self._not_set_up[declaration.name] = TypeError(str(e))
                else:
                    try:
                        # `as_protocol` cannot take the generic `HasSetup`, which
                        # mypy refuses as a type form; the class was checked above
                        ready = cast("HasSetup[...]", instance)
                        store.inject(setup_call(ready, declaration.name, answers))()
                        continue
                    except Exception as e:  # noqa: BLE001 - a setup must not abort the app
                        self._not_set_up[declaration.name] = e
            logger.warning(
                "Failed to set up %s '%s': %s",
                declaration.kind,
                declaration.name,
                self._not_set_up[declaration.name],
            )

    def _answers_for(
        self,
        declaration: Declaration,
        questions: Mapping[str, tuple[Shape, type]],
        built: Mapping[str, object],
    ) -> dict[str, object]:
        """Answer the protocol questions *declaration*'s `setup` asks.

        A census reads the components; one answer may also be a value a
        component shares. A single answer from a later layer is refused, as a
        value from one is.

        Raises
        ------
        NoAnswer
            Naming the components that failed to build, when exactly one
            answer was demanded and only they could have given it.
        TypeError
            If several objects answer where one was asked for, none does and
            nothing that failed would have, or the answer comes from a later
            layer.
        """
        answers: dict[str, object] = {}
        for pname, (shape, protocol) in questions.items():
            where = f"{declaration.name!r} in its {pname!r} parameter"
            try:
                value, owners = answer(
                    shape, protocol, declaration.name, built, self._shared_values, where
                )
            except NoAnswer as e:
                failed = [
                    d.name
                    for d in self._declarations.values()
                    if d.name in self._failed and _structural.satisfies(d.cls, protocol)
                ]
                if not failed:
                    raise TypeError(str(e) + near_misses(built, protocol)) from None
                raise NoAnswer(f"{listed(failed)} was not built") from None
            if shape != "every":
                for owner in owners:
                    target = self._declarations.get(owner)
                    if target is not None:
                        refuse_backwards(
                            declaration, target, f"its {pname!r} parameter"
                        )
            self._answered.update(owners)
            answers[pname] = value
        return answers

    def _construct(self, layer: Layer) -> None:
        """Build every component of *layer* and register what it shares.

        A component is registered under its own key, and under its class when
        no other declaration names that class, so a collaborator may ask for it
        either way.

        The order is the order the layer declares them in: a component takes
        nothing another component owns, so nothing has to be built first. One
        that cannot be built is logged and skipped, so that a session missing a
        part of itself still comes up.

        Raises
        ------
        RuntimeError
            If the registry step has not opened the store yet.
        """
        store = self._store
        if store is None:
            raise RuntimeError("The registry step has to run before a component is")
        declarations = [d for d in self._components() if d.kind is layer]
        view_arguments = self.view_arguments if layer is Layer.VIEW else {}
        for declaration in declarations:
            passed = {
                **view_arguments,
                **{
                    pname: satisfying(self._devices, protocol)
                    for pname, protocol in device_questions(
                        declaration.cls, declaration.cfg_kwargs
                    ).items()
                },
            }
            params = injectable(declaration.cls, declaration.cfg_kwargs, passed=passed)
            if self._refuse_or_skip(store, declaration, params):
                continue
            try:
                instance = store.inject(factory(declaration, self._on_built, passed))()
            except Exception as e:  # noqa: BLE001 - a missing component must not abort the app
                self._skip(declaration, e)
                continue
            store.register_provider(constant(instance), type_hint=declaration.key)
            if self._is_unique(declaration):
                store.register_provider(constant(instance), type_hint=declaration.cls)
            shared = register_shared(
                store, instance, declaration.cls, declaration.name, self._shared
            )
            self._shared_values.extend((declaration.name, value) for value in shared)
            if isinstance(instance, DocumentRouter):
                self._callbacks[declaration.name] = instance

    def _refuse_or_skip(
        self,
        store: Store,
        declaration: Declaration,
        params: Mapping[str, Any],
    ) -> bool:
        """Return whether *declaration* is skipped for want of a collaborator.

        A parameter left unanswered by a component this build already failed
        on is a consequence of that failure, and skipping is what the session
        does with it. One nothing ever declared is a mistake in the session
        and still raises.

        Raises
        ------
        TypeError
            Naming the parameters and the types nothing answers.
        """
        missing = unanswered(store, params)
        if not missing:
            return False
        absent = self._blamed(hint for _, hint in missing)
        if not absent:
            raise TypeError(unanswered_message(declaration.name, missing))
        named = listed(sorted(absent))
        reason = TypeError(f"{named} was not built")
        self._skip(declaration, reason)
        return True

    def _blamed(self, hints: Iterable[object]) -> set[str]:
        """Return the names of failed components that would have answered *hints*.

        A component registers itself under its key and, when it is the only
        declaration naming its class, under that class too, and it registers
        every type it shares, so those are the ways a collaborator can have
        asked for it.
        """
        wanted = set(hints)
        return {
            declaration.name
            for declaration in self._declarations.values()
            if declaration.name in self._failed
            and (
                declaration.key in wanted
                or (declaration.cls in wanted and self._is_unique(declaration))
                or wanted & set(shared_keys(declaration.cls).values())
            )
        }

    def _skip(self, declaration: Declaration, reason: BaseException) -> None:
        """Record and report a component the session is going on without."""
        self._failed[declaration.name] = reason
        logger.error(
            "Failed to build %s '%s': %s", declaration.kind, declaration.name, reason
        )

    def _check_layers(self, declarations: list[Declaration]) -> None:
        """Refuse a component whose `setup` reaches into a later layer.

        Every component exists when `setup` runs, so this is a rule about
        direction rather than a consequence of the build order: a presenter
        does not know about views.

        Raises
        ------
        TypeError
            If a component takes a value a later layer owns.
        """
        by_type = owners(declarations)
        routers = [d for d in declarations if issubclass(d.cls, DocumentRouter)]
        for declaration in declarations:
            if not issubclass(declaration.cls, HasSetup):
                continue
            for pname, hint in get_setup_params(declaration.cls).items():
                wanted = optional_arg(hint) or hint
                where = f"its {pname!r} parameter"
                if wanted == CallbackCatalogue:
                    for router in routers:
                        refuse_backwards(declaration, router, where)
                target = by_type.get(wanted)
                if target is None:
                    continue
                refuse_backwards(declaration, target, where)

    def _refuse_component_values(self, declarations: list[Declaration]) -> None:
        """Refuse a constructor taking something another component owns.

        A component is constructed before its peers, so only `setup` can be
        given a component, its class, or a type another component shares.

        Raises
        ------
        TypeError
            Naming the parameter and the component that owns what it asks for.
        """
        by_type = owners(declarations)
        by_type.update({d.key: d for d in declarations})
        for declaration in declarations:
            for pname, hint in injectable(
                declaration.cls, declaration.cfg_kwargs
            ).items():
                wanted = optional_arg(hint) or hint
                target = by_type.get(wanted)
                if wanted == CallbackCatalogue:
                    raise TypeError(
                        f"{declaration.name!r} takes the callback catalogue in "
                        f"its {pname!r} parameter, which no component exists to "
                        "fill yet; ask for it in 'setup'."
                    )
                if target is not None:
                    raise TypeError(
                        f"{declaration.name!r} takes {target.name!r} in its "
                        f"{pname!r} parameter, and a component is constructed "
                        "before its peers; ask for it in 'setup'."
                    )

    @overload
    def _built(self, layer: Literal[Layer.PRESENTER]) -> dict[str, NamedComponent]: ...
    @overload
    def _built(self, layer: Literal[Layer.VIEW]) -> dict[str, AttachableComponent]: ...
    def _built(self, layer: Layer) -> dict[str, Any]:
        return {
            d.name: d.instance
            for d in self._declarations.values()
            if d.kind is layer and d.instance is not None
        }

    def _verify(self, declaration: Declaration, instance: object) -> None:
        """Check a component just built against the protocol of its layer.

        A member assigned in ``__init__`` is invisible on the class, so a view
        answering ``placement`` from anything but a class attribute is only
        checkable now.

        Raises
        ------
        TypeError
            If the instance does not satisfy its layer's protocol, or asks for
            a placement the frontend cannot attach it to.
        """
        view = declaration.kind is Layer.VIEW
        protocol: type = AttachableComponent if view else NamedComponent
        reasons = _structural.problems(instance, protocol)
        if reasons:
            raise TypeError(
                f"{declaration.name!r} is declared as a {declaration.kind}, but "
                f"does not satisfy {protocol.__name__!r}: " + "; ".join(reasons)
            )
        attachable = as_protocol(instance, AttachableComponent) if view else None
        if attachable is not None:
            self.frontend.check_placement(
                attachable, attachable.placement, f"view {declaration.name!r}"
            )

    def _is_unique(self, declaration: Declaration) -> bool:
        others = [d for d in self._components() if d.cls is declaration.cls]
        if len(others) == 1:
            return True
        logger.debug(
            "%s is declared as %s; it can only be injected by name",
            declaration.cls.__name__,
            ", ".join(d.name for d in others),
        )
        return False

    def _read_transport(self, config: Mapping[str, Any]) -> str:
        """Return the transport *config* names under ``services``, checked.

        Raises
        ------
        TypeError
            If it is not one ``redsun`` has, or the key holds a service entry.
        """
        named = transport_of(config)
        if named is None:
            return CHANNEL_ACCESS
        if not isinstance(named, str):
            raise TypeError(
                f"{TRANSPORT_KEY!r} is reserved in the services section for what "
                f"the services speak and cannot name a service"
            )
        return checked_transport(named, f"{type(self).__qualname__}'s services")

    def start_services(self) -> None:
        """Start the launched services together, and attach to the rest.

        The step takes as long as the slowest service. A service that does not
        start is logged, and devices naming it are skipped. Each stop is a
        release, so `shutdown` stops services after every component, the last
        declared first, then drops what the transport caches about them so a
        rebuilt session reconnects at once.
        """
        self._failed_services = {}
        self._start_catalog()
        if not self._services:
            return
        self.on_release(lambda: run_coro(TRANSPORTS[self._transport].release()))
        with ThreadPoolExecutor(len(self._services), "service-start") as pool:
            starts = {
                name: pool.submit(service.start)
                for name, service in self._services.items()
            }
        for name, start in starts.items():
            error = start.exception()
            if error is not None:
                self._failed_services[name] = error
                logger.error("Failed to start service '%s': %s", name, error)
            elif self._services[name].launched:
                self.on_release(self._services[name].stop)
        started = len(self._services) - len(self._failed_services)
        summary = f"Services started: {started}/{len(self._services)}"
        failed = ", ".join(f"{n} ({e})" for n, e in self._failed_services.items())
        if failed:
            logger.warning("%s\nNot started: %s", summary, failed)
        else:
            logger.info(summary)

    def _start_catalog(self) -> None:
        """Start the catalog the storage section asks for, or log why it could not.

        It is stopped after every component and service, being released first.
        """
        catalog = self.storage.catalog
        if catalog is None:
            return
        try:
            self._catalog = start_catalog(catalog, self.path_provider)
        except Exception as e:  # noqa: BLE001 - a catalog that fails must not abort the app
            logger.error("Failed to start the catalog: %s", e)
            return
        self.on_release(self._close_catalog)

    def _close_catalog(self) -> None:
        """Stop the session's catalog."""
        if self._catalog is not None:
            self._catalog.close()
            self._catalog = None

    def build_devices(self) -> None:
        """Construct the devices, which are built from no other component.

        They come before the store because a device is made from its own
        declaration and asks the session for nothing. A device naming a service
        receives that service's prefix as ``prefix``, and is skipped when the
        service is not declared, did not start, or gives no prefix.
        """
        for declaration in self._declarations.values():
            if declaration.kind is not Layer.DEVICE or declaration.refusal is not None:
                continue
            try:
                device = declaration.cls(
                    name=declaration.name,
                    **declaration.cfg_kwargs,
                    **self._prefix_for(declaration),
                    **self._path_provider_for(declaration),
                )
            except Exception as e:  # noqa: BLE001 - a missing device must not abort the app
                self._failed[declaration.name] = e
                logger.error("Failed to build device '%s': %s", declaration.name, e)
                continue
            self._devices[declaration.name] = device
            declaration.instance = device
            setattr(self, declaration.name, device)
            self._register_teardown(device)

    def _prefix_for(self, declaration: Declaration) -> dict[str, str]:
        """Return the ``prefix`` keyword from *declaration*'s service, if it names one.

        Raises
        ------
        LookupError
            If the device names a service that is not declared.
        RuntimeError
            If the device names a service that did not start.
        ValueError
            If the device names a service that gives no prefix.
        """
        if declaration.service is None:
            return {}
        service = self._services.get(declaration.service)
        if service is None:
            raise LookupError(f"service {declaration.service!r} is not declared")
        if declaration.service in self._failed_services:
            raise RuntimeError(f"service {declaration.service!r} was not started")
        if not service.prefix:
            raise ValueError(f"service {declaration.service!r} gives no prefix")
        return {"prefix": service.prefix}

    def _path_provider_for(self, declaration: Declaration) -> dict[str, object]:
        """Return the ``path_provider`` keyword, for a device whose constructor takes it."""
        parameter = inspect.signature(declaration.cls).parameters.get("path_provider")
        if parameter is None or parameter.kind not in (
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        ):
            return {}
        return {"path_provider": self.path_provider}

    def connect_built_devices(self) -> None:
        """Connect every autoconnect device at once.

        A device not connected within `CONNECT_TIMEOUT` is dropped and recorded
        as failed, like one that fails to build.
        """
        targets = {
            name: device
            for name, device in self._devices.items()
            if self._declarations[name].autoconnect
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
            declaration = self._declarations[name]
            reason = self._connection_failure(declaration, result)
            self._failed[name] = ConnectionError(reason)
            del self._devices[name]
            declaration.instance = None
            delattr(self, name)
            logger.error("Failed to connect device '%s': %s", name, reason)

    def _connection_failure(
        self, declaration: Declaration, error: BaseException
    ) -> str:
        """Return why *declaration*'s device did not connect, naming its service."""
        # ophyd-async pads the message of a NotConnectedError with whitespace
        detail = str(error).strip()
        service = self._services.get(declaration.service or "")
        if service is None:
            return detail
        how = "launched" if service.launched else "attached"
        return (
            f"service {service.name!r} ({how}) did not answer within "
            f"{CONNECT_TIMEOUT:g} s: {detail}"
        )

    def _on_built(self, declaration: Declaration, instance: NamedComponent) -> None:
        self._verify(declaration, instance)
        declaration.instance = instance
        setattr(self, declaration.name, instance)
        self._register_teardown(instance)

    def _register_teardown(self, component: object) -> None:
        """Hand the session's own teardown to the one owner of it.

        A component that declares ``shutdown`` is finalized without having to
        ask for it; one that does not needs no teardown at all.
        """
        if not isinstance(component, HasShutdown):
            return
        shutdown = component.shutdown
        # both protocols name one method, so only the function says which it is
        if not inspect.iscoroutinefunction(shutdown):
            self.on_release(shutdown)
            return

        async_shutdown = cast("HasAsyncShutdown", component).shutdown

        def close() -> None:
            run_coro(async_shutdown())

        self.on_release(close)

    def _apply_wiring_config(self, config: Mapping[str, Any]) -> None:
        """Connect the port pairs the ``wiring`` section lists.

        A rule naming a component the build failed on is warned about and
        skipped, so one component that could not be made does not keep the
        session from coming up. Every other way of getting a rule wrong stays
        fatal, a name that was never declared included.

        Raises
        ------
        WiringError
            If a rule is not a mapping of exactly ``from`` and ``to``, or
            names a port that cannot be resolved for any other reason.
        """
        for index, rule in enumerate(config.get("wiring", [])):
            if not isinstance(rule, dict) or rule.keys() != {"from", "to"}:
                raise WiringError(
                    f"wiring entry {index} must be a mapping with exactly the "
                    f"keys 'from' and 'to', got {rule!r}"
                )
            try:
                self.connect_paths(rule["from"], rule["to"])
            except ComponentNotBuilt as e:
                if e.component not in self._failed:
                    raise
                logger.warning(
                    "Not connecting %s -> %s: component %r was not built",
                    rule["from"],
                    rule["to"],
                    e.component,
                )

    def _warn_unused(self) -> None:
        """Report a component and a shared value the session never uses.

        Both are legal, so neither stops the build: a session under
        construction has components nothing reaches yet, and a bundle may ship
        one a particular session does not need.

        Runs after the wiring, which is the last thing that can put a
        component to use.
        """
        declarations = [d for d in self._components() if d.instance is not None]
        wanted = {
            optional_arg(hint) or hint
            for declaration in declarations
            for hint in self._asked_for(declaration)
        }
        used = self._used(declarations, wanted)
        for declaration in declarations:
            provided = shared_keys(declaration.cls)
            for method, key in provided.items():
                if key not in wanted:
                    logger.warning(
                        "%s.%s shares %r, which no component asks for",
                        declaration.name,
                        method,
                        getattr(key, "__name__", key),
                    )
            self._warn_double_route(declaration, declarations)
            requires = list(self._asked_for(declaration))
            if not provided and not requires and declaration.name not in used:
                logger.warning(
                    "%r shares nothing, asks for nothing and is wired to nothing; "
                    "it is built and reachable, and does nothing",
                    declaration.name,
                )

    def _asked_for(self, declaration: Declaration) -> list[Any]:
        """Return every type *declaration* asks for, constructor and `setup`."""
        return [
            *injectable(declaration.cls, declaration.cfg_kwargs).values(),
            *device_questions(declaration.cls, declaration.cfg_kwargs).values(),
            *(
                get_setup_params(declaration.cls).values()
                if issubclass(declaration.cls, HasSetup)
                else ()
            ),
        ]

    def _warn_double_route(
        self, declaration: Declaration, declarations: list[Declaration]
    ) -> None:
        """Report a component that both holds another and publishes to it.

        Two routes to one component means an action written both ways runs
        twice. Which method a component calls is not knowable here, so a pair
        using each route for something different is named once and legally.
        """
        by_type = owners(declarations)
        by_type.update({d.key: d for d in declarations})
        held = {
            by_type[asked].name
            for asked in (
                optional_arg(hint) or hint for hint in self._asked_for(declaration)
            )
            if asked in by_type
        }
        for connection in self.connections:
            if connection.publisher == declaration.name and connection.consumer in held:
                logger.warning(
                    "%r holds %r and is also connected to it; a bundle reaches a "
                    "component one way, by calling it or by a signal",
                    declaration.name,
                    connection.consumer,
                )

    def _used(self, declarations: list[Declaration], wanted: set[Any]) -> set[str]:
        """Check the components something in the session reaches.

        *wanted* is every type a constructor asks for, so a component another
        one is built from counts, by its key or by its class, and a router
        counts when something asks for the callback catalogue.
        """
        names = {c.publisher for c in self.connections}
        if CallbackCatalogue in wanted:
            names |= {d.name for d in declarations if issubclass(d.cls, DocumentRouter)}
        names |= {c.consumer for c in self.connections}
        names |= {s.consumer for s in self.subscriptions}
        names |= self._answered
        names |= {
            declaration.name
            for declaration in declarations
            if declaration.key in wanted or declaration.cls in wanted
        }
        return names


def unanswered(store: Store, params: Mapping[str, Any]) -> list[tuple[str, object]]:
    """Return the parameters of *params* nothing in the store answers.

    Everything a component may be built from is registered by the time it is
    reached, so a parameter with no provider has none coming.
    """
    return [
        (pname, hint)
        for pname, hint in params.items()
        if optional_arg(hint) is None and next(store.iter_providers(hint), None) is None
    ]


def unanswered_message(name: str, missing: list[tuple[str, object]]) -> str:
    """Return the refusal naming what *name* asked for and did not get."""
    named = listed(
        [f"{pname!r} ({getattr(hint, '__name__', hint)})" for pname, hint in missing],
        quote=False,
    )
    return (
        f"{name!r} asks for {named}, which nothing in the session provides. "
        "A component names the values it needs, and the session is not one of "
        "them."
    )


def refuse_unanswered(store: Store, name: str, params: Mapping[str, Any]) -> None:
    """Refuse *name* asking for something the session does not hold.

    Raises
    ------
    TypeError
        Naming the parameters and the types nothing answers.
    """
    missing = unanswered(store, params)
    if missing:
        raise TypeError(unanswered_message(name, missing))


def owners(
    declarations: list[Declaration],
) -> dict[Any, Declaration]:
    """Return every type naming a component, by the declaration answering it.

    A class declared twice is left out: nothing can be injected by it, so no
    edge can name it.
    """
    counts: dict[type, int] = {}
    for declaration in declarations:
        counts[declaration.cls] = counts.get(declaration.cls, 0) + 1
    found: dict[Any, Declaration] = {}
    for declaration in declarations:
        if counts[declaration.cls] == 1:
            found[declaration.cls] = declaration
        for provided in shared_keys(declaration.cls).values():
            found[provided] = declaration
    return found


def refuse_backwards(
    asker: Declaration,
    target: Declaration,
    where: str,
) -> None:
    """Refuse *asker* taking *target*, when *target* is in a later layer."""
    if ORDER[target.kind] <= ORDER[asker.kind]:
        return
    raise TypeError(
        f"{asker.name!r} is a {asker.kind} and {where} asks for "
        f"{target.name!r}, which is a {target.kind}. A {asker.kind} knows "
        f"nothing about a {target.kind}; share the value the other way, or "
        "move what they both need into an earlier layer."
    )


def as_protocol(instance: object, protocol: TypeForm[P]) -> P | None:
    """Return *instance* typed as the runtime-checkable *protocol*, or ``None``.

    Returning the value rather than a `TypeIs` keeps narrowing out of the
    caller: mypy reports a check of a union of a class and a protocol against
    another protocol as unreachable.
    """
    # the protocols passed are classes at runtime
    return cast("P", instance) if isinstance(instance, cast("type", protocol)) else None


def listed(names: Iterable[str], *, quote: bool = True) -> str:
    """Return *names* as an English list, empty reading as "nothing".

    Quoted unless the caller has already formatted each item.
    """
    items = [repr(name) for name in names] if quote else list(names)
    if len(items) < 2:
        return items[0] if items else "nothing"
    return f"{', '.join(items[:-1])} and {items[-1]}"


def near_misses(components: Mapping[str, object], protocol: type) -> str:
    """Report the components that carry some of *protocol*, and why not all."""
    return "".join(
        f"\n  {name!r}: " + "; ".join(reasons)
        for name, reasons in rejected(components, protocol).items()
    )


def base_for(cls: type[Session], frontend: object) -> type[Session]:
    """Return the class a session naming *frontend* is built on.

    A session class already built against that toolkit is kept, so a subclass
    carrying its own declarations stays the one instantiated.
    """
    if frontend is None:
        return cls
    dotted = FRONTENDS.get(str(frontend))
    if dotted is None:
        raise ValueError(
            f"the configuration names frontend {frontend!r}, which no session "
            f"is built against. Known: {', '.join(sorted(FRONTENDS))}."
        )
    module_name, _, class_name = dotted.partition(":")
    resolved: type[Session] = getattr(import_module(module_name), class_name)
    if issubclass(cls, resolved):
        return cls
    if cls is not Session:
        raise TypeError(
            f"the configuration names frontend {frontend!r}, which builds on "
            f"{resolved.__name__}, but from_config was called on "
            f"{cls.__name__}, which is not one of those."
        )
    return resolved


def instantiate(declaration: HookDeclaration, owner: str) -> object:
    """Construct the provider *declaration* names.

    Raises
    ------
    HookError
        If the class rejects the keys given.
    """
    named = ", ".join(repr(moment) for moment in declaration.moments)
    try:
        return declaration.cls(**declaration.kwargs)
    except TypeError as e:
        raise HookError(
            f"cannot construct hook provider {declaration.cls.__name__!r} "
            f"declared on {owner} at {named} with "
            f"{sorted(declaration.kwargs)}: {e}"
        ) from e
