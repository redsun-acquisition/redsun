from __future__ import annotations

import asyncio
import inspect
import logging
from collections.abc import Mapping, Sequence  # noqa: TC003
from contextlib import ExitStack, nullcontext
from copy import deepcopy
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Final, Self, cast

import yaml
from in_n_out import Store
from ophyd_async.core import Device  # noqa: TC002
from psygnal import SignalInstance

from redsun import _structural
from redsun._config import Source, as_sources, load
from redsun._hooks import HookError, parse_hook_specs, resolve_hooks
from redsun.aio import run_coro
from redsun.experimental._settings import Settings
from redsun.experimental.session import (
    _declarations,
    _factories,
    _plugins,
)
from redsun.experimental.session._declarations import Layer
from redsun.experimental.session._frontend import Frontend
from redsun.experimental.session._protocols import (
    AttachableComponent,
    BuildableSession,
    NamedComponent,
    Serializable,
)
from redsun.experimental.virtual import _provides
from redsun.experimental.virtual._requires import (
    Devices,
    Maybe,
    One,
    Satisfying,
    key_for,
)
from redsun.experimental.virtual._shared import (
    BlueskyCallbackRegistry,
    CallbackType,
    DeviceMapping,
    SessionConfig,
)
from redsun.experimental.virtual._wiring import (
    SLOT_ATTR,
    SLOT_THREAD_ATTR,
    ComponentNotBuilt,
    Connection,
    SessionNotBuilt,
    Slot,
    Subscription,
    Unconnected,
    WiringError,
    owner_of,
    port_name,
    ports,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable
    from contextlib import AbstractContextManager

    from bluesky.protocols import HasName
    from ophyd_async.core import SignalR

    from redsun.experimental.session._declarations import Key
    from redsun.experimental.virtual._requires import Question
    from redsun.experimental.virtual._wiring import SlotThread

__all__ = ["ConfigurationInUse", "Session"]


class ConfigurationInUse(OSError):
    """Raised when a session is asked to write over a source it was built from.

    A saved file is one flat session, where a source may be shared by several
    and hand-written. Overwriting one replaces what those other sessions read.
    """

    def __init__(self, path: Path) -> None:
        super().__init__(f"{path} is a source this session was built from")
        self.path = path


logger = logging.getLogger("redsun")


def _unaccepted(cls: type, entry: Mapping[str, object]) -> list[str]:
    """Return the keys of *entry* that *cls* would refuse to be built from.

    The constructor's parameters decide this, not the keys the configuration
    carried. A component serializes every parameter it has, including one
    that took its default and that no source named, and that key is correct.
    A constructor taking ``**kwargs`` accepts anything, so it refuses none.
    """
    params = _factories.constructor(cls).parameters
    if any(p.kind is p.VAR_KEYWORD for p in params.values()):
        return []
    return sorted(set(entry) - {name for name in params if name != "name"})


def _silent(step: str) -> None:
    """Take a build step's name and do nothing with it.

    What a session reports progress to when no hook asked for it, so the
    build has one path whether or not anything is watching.
    """


_ORDER: Final[dict[Layer, int]] = {Layer.DEVICE: 0, Layer.PRESENTER: 1, Layer.VIEW: 2}
"""The order the layers are built in, which is the order they may depend in."""

_BUILD_STEPS: Final[tuple[str, ...]] = (
    "devices",
    "registry",
    "presenters",
    "views",
    "seal",
    "wiring",
    "presentation",
    "report",
)
"""The steps a build reports, in order, to whatever is watching it.

A `during_build` hook is told one of these names as each step starts, so a
progress display that counts them needs the total in advance to show how far
along it is. It is private while this layer is: a hook reaching it is reaching
into the module, and publishing it is part of the layer graduating.

`Session.build` runs two steps before the first of these, reading the
configuration and starting the toolkit's runtime, and reports neither. A hook
covering the build is a toolkit object itself, a splash screen being the case
it was written for, so nothing can be watching until the runtime that shows it
exists.
"""

_FRONTENDS: Final[dict[str, str]] = {
    "pyqt": "redsun.experimental.session.qt:QtSession",
    "pyside": "redsun.experimental.session.qt:QtSession",
}
"""The session class a configuration's frontend name builds on."""


class Session(BuildableSession):
    """One running application, whose components are declared as annotations.

    ```python
    class MyApp(QtSession):
        __slots__ = ()

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

    Declarations are annotations, so they claim no slot and no class
    attribute; a subclass adding ``__slots__ = ()`` keeps its instances free
    of a ``__dict__``.
    """

    __slots__ = (
        "__weakref__",
        "_answers",
        "_baseline",
        "_built_components",
        "_callbacks",
        "_config",
        "_connections",
        "_declarations",
        "_devices",
        "_failed",
        "_hooks",
        "_is_built",
        "_links",
        "_merged",
        "_names",
        "_registry",
        "_releases",
        "_report",
        "_sealed",
        "_session_config",
        "_settings",
        "_shared",
        "_store",
        "_subscription_records",
        "_subscriptions",
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
        self._report: Callable[[str], None] = _silent
        self._releases = ExitStack()
        self._declarations: dict[str, _declarations.Declaration] = {}
        self._devices: dict[str, Device] = {}
        # what the build could not make, by component name, so that a
        # component built from one of them is skipped rather than refused
        self._failed: dict[str, BaseException] = {}
        self._answers: dict[Question, _declarations.Declaration | None] = {}
        self._baseline: dict[str, Mapping[str, object]] = {}
        self._session_config = SessionConfig()
        self._callbacks: dict[str, CallbackType] = {}
        self._built_components: dict[str, object] = {}
        self._names: dict[int, str] = {}
        self._sealed = False
        self._links: list[tuple[SignalInstance, Callable[..., Any]]] = []
        self._connections: list[Connection] = []
        # the forwarding function is held because ophyd-async releases a
        # subscription by identity: clear_sub needs the object back
        self._subscriptions: list[
            tuple[SignalR[Any], Callable[[Any], None], SignalInstance]
        ] = []
        self._subscription_records: list[Subscription] = []
        self._registry = BlueskyCallbackRegistry(self._callbacks, lambda: self._sealed)
        self._settings: Settings | None = None
        self._store: Store | None = None
        # the component sharing each key, carried across the layer steps so
        # that a presenter and a view offering one type still clash
        self._shared: dict[Key, str] = {}
        self._is_built = False

    def __getattr__(self, name: str) -> Any:
        """Return the built component *name*."""
        # an unassigned slot lands here too, and answering it by reading
        # _declarations would recurse; component names are never underscored
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            declarations = object.__getattribute__(self, "_declarations")
        except AttributeError:
            raise AttributeError(name) from None
        if name in declarations:
            return declarations[name].instance
        raise AttributeError(f"{type(self).__name__!r} declares no component {name!r}")

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
        return cast("Self", _base_for(cls, config.get("frontend"))(config))

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
    def declarations(self) -> Mapping[str, _declarations.Declaration]:
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
        for moment, declaration in _declarations.read_hooks(type(self), points).items():
            provider = built.get(id(declaration))
            if provider is None:
                provider = _instantiate(declaration, owner)
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
        shared: dict[Key, str] = {}
        classes: dict[str, type] = {cls.__name__: cls for cls in self.providers}
        classes.update(_plugins.load_providers(config))
        for name, cls in classes.items():
            params = _factories.injectable(cls, {}, binds_name=False)
            _refuse_unanswered(store, name, params)
            instance = store.inject(_factories.provider(cls, name))()
            _provides.register(store, instance, cls, name, shared)

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
                    ("devices", self.build_devices),
                    ("registry", self.open_registry),
                    ("presenters", self.build_presenters),
                    ("views", self.build_views),
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
        config = self._configuration()
        logger.debug("Hooks installed at: %s", ", ".join(self.hooks) or "no points")
        self._set_configuration(config, self.name)
        self._declarations = _declarations.read(type(self), config, self.frontend)

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
        store.register_provider(_constant(self._settings), type_hint=Settings)
        self._register_framework_values(store, lambda: dict(self._devices))
        self._share(store, self._configuration())
        declarations = self._components()
        self._check_layers(declarations)
        self._answer(store, declarations)

    def seal(self) -> None:
        """Check what was built, then close the session to further building."""
        self._verify_components()
        self._verify_answers()
        self._set_components(
            {
                declaration.name: declaration.instance
                for declaration in self._components()
                if declaration.instance is not None
            }
        )
        self._seal()
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
        if self._failed:
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
        if not self._failed:
            return summary
        missing = ", ".join(
            f"{name} ({self._declarations[name].kind})" for name in self._failed
        )
        return summary + "\nNot built: " + missing

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
        self._sealed = False
        self.disconnect_all()
        self._releases.close()
        self._callbacks.clear()
        self._built_components.clear()
        self._names.clear()
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
        return {
            declaration.name: declaration.instance.serialize()
            for declaration in self._declarations.values()
            if isinstance(declaration.instance, Serializable)
        }

    def _entry_for(
        self, declaration: _declarations.Declaration
    ) -> dict[str, Any] | None:
        """Return the entry *declaration*'s component asks to be written.

        ``None`` where there is nothing to write, which leaves the entry the
        session loaded in place. One refused key discards the whole entry
        rather than only itself: dropping the key alone would leave an entry
        the component never asked for, where a renamed setting writes the new
        key, loses it, and keeps the old one beside values that assume the
        rename.
        """
        instance = declaration.instance
        if instance is None or not isinstance(instance, Serializable):
            return None
        entry = dict(instance.serialize())
        unaccepted = _unaccepted(declaration.cls, entry)
        if not unaccepted:
            return entry
        logger.warning(
            "'%s' tried to save %s, which %s does not accept; keeping the "
            "entry as loaded",
            declaration.name,
            ", ".join(unaccepted),
            type(instance).__name__,
        )
        return None

    def _register_framework_values(
        self, store: Store, devices: Callable[[], DeviceMapping]
    ) -> None:
        """Register everything the framework knows on *store*.

        Every component may ask for it by type. The callback registry is a live
        view, so it is available at construction like the rest and carries no
        ordering constraint of its own.
        """
        store.register_provider(lambda: self._session_config, type_hint=SessionConfig)
        store.register_provider(devices, type_hint=DeviceMapping)
        store.register_provider(
            lambda: self._registry, type_hint=BlueskyCallbackRegistry
        )

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

    def register_callbacks(
        self,
        owner: HasName,
        name: str | None = None,
        callback_map: dict[str, CallbackType] | None = None,
    ) -> None:
        """Register one or more document callbacks.

        Parameters
        ----------
        owner : HasName
            The component registering callbacks, and the callback itself when
            *callback_map* is ``None``.
        name : str | None
            Registry key for *owner*. Defaults to ``owner.name``; ignored when
            *callback_map* is given.
        callback_map : dict[str, CallbackType] | None
            Several callbacks from one owner, each registered under its own
            key. *owner* is then not registered itself.

        Raises
        ------
        TypeError
            If a callback is not callable or its signature is incompatible
            with ``(str, Document)``.
        """
        self._registry.register(owner, name=name, callback_map=callback_map)

    @property
    def callbacks(self) -> dict[str, CallbackType]:
        """The currently registered document callbacks."""
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
        declaration = getattr(slot, SLOT_ATTR, None)
        if not isinstance(declaration, Slot):
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
        component = self._built_components.get(component_name)
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

    def satisfying(self, protocol: type) -> Satisfying:
        """Return a live view of the built components satisfying *protocol*."""
        return Satisfying(protocol, self._built_components, lambda: self._sealed)

    def _seal(self) -> None:
        """Mark the build complete, making the live views readable."""
        self._sealed = True

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

    def _built(self, layer: Layer) -> dict[str, Any]:
        return {
            d.name: d.instance
            for d in self._declarations.values()
            if d.kind is layer and d.instance is not None
        }

    def _components(self) -> list[_declarations.Declaration]:
        return [d for d in self._declarations.values() if d.kind is not Layer.DEVICE]

    def build_presenters(self) -> None:
        """Construct the presenter layer, in the order it depends in."""
        self._construct(Layer.PRESENTER)

    def build_views(self) -> None:
        """Construct the view layer, in the order it depends in."""
        self._construct(Layer.VIEW)

    def _construct(self, layer: Layer) -> None:
        """Build every component of *layer* and register what it shares.

        A component is registered under its own key, and under its class when
        no other declaration names that class, so a collaborator may ask for it
        either way.

        One that cannot be built is logged and skipped, and so is one built
        from it, so that a session missing a part of itself still comes up.

        Raises
        ------
        RuntimeError
            If the registry step has not opened the store yet.
        """
        store = self._store
        if store is None:
            raise RuntimeError("The registry step has to run before a component is")
        declarations = [d for d in self._components() if d.kind is layer]
        chosen_for = self._chosen_for(declarations)
        shared = self._shared
        for declaration in self._ordered(declarations):
            absent = chosen_for.get(declaration.name, set()) & set(self._failed)
            if absent:
                named = _listed_plain(sorted(repr(name) for name in absent))
                self._skip(declaration, TypeError(f"{named} was not built"))
                continue
            params = _factories.injectable(declaration.cls, declaration.cfg_kwargs)
            if self._refuse_or_skip(store, declaration, params):
                continue
            factory = _factories.factory(declaration, self._on_built)
            try:
                instance = store.inject(factory)()
            except SessionNotBuilt:
                # a component asking the session a question it cannot answer
                # yet is written wrongly, which is not a part being absent
                raise
            except Exception as e:  # noqa: BLE001 - a missing component must not abort the app
                self._skip(declaration, e)
                continue
            store.register_provider(_constant(instance), type_hint=declaration.key)
            if self._is_unique(declaration):
                store.register_provider(_constant(instance), type_hint=declaration.cls)
            _provides.register(
                store, instance, declaration.cls, declaration.name, shared
            )

    def _chosen_for(
        self, declarations: list[_declarations.Declaration]
    ) -> dict[str, set[str]]:
        """Return, by asker, the components chosen for the questions it asks.

        Only a question demanding exactly one component is here. One that
        allows none is answered with nothing when the component chosen for it
        cannot be built, which is an answer the asker already accepts.
        """
        found: dict[str, set[str]] = {}
        for question, askers in _factories.requirements(declarations).items():
            chosen = self._answers.get(question)
            if chosen is None or not isinstance(question.marker, One):
                continue
            for asker in askers:
                found.setdefault(asker, set()).add(chosen.name)
        return found

    def _refuse_or_skip(
        self,
        store: Store,
        declaration: _declarations.Declaration,
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
        unanswered = _unanswered(store, params)
        if not unanswered:
            return False
        absent = self._blamed(hint for _, hint in unanswered)
        if not absent:
            raise TypeError(_unanswered_message(declaration.name, unanswered))
        named = _listed_plain(sorted(repr(name) for name in absent))
        reason = TypeError(f"{named} was not built")
        self._skip(declaration, reason)
        return True

    def _blamed(self, hints: Iterable[object]) -> set[str]:
        """Return the names of failed components that would have answered *hints*.

        A component registers itself under its key and, when it is the only
        declaration naming its class, under that class too, so those are the
        two ways a collaborator can have asked for it.
        """
        wanted = set(hints)
        return {
            declaration.name
            for declaration in self._declarations.values()
            if declaration.name in self._failed
            and (
                declaration.key in wanted
                or (declaration.cls in wanted and self._is_unique(declaration))
            )
        }

    def _skip(
        self, declaration: _declarations.Declaration, reason: BaseException
    ) -> None:
        """Record and report a component the session is going on without."""
        self._failed[declaration.name] = reason
        logger.error(
            "Failed to build %s '%s': %s", declaration.kind, declaration.name, reason
        )

    def _ordered(
        self, declarations: list[_declarations.Declaration]
    ) -> list[_declarations.Declaration]:
        """Return *declarations* in the order they have to be built.

        Layers first, since `_check_layers` has already refused an edge
        pointing the other way. Within a layer the order is what depends on
        what, which declaration order does not give: a component may be
        written above the one it is built from.
        """
        needs = self._edges(declarations)
        ordered: list[_declarations.Declaration] = []
        for layer in sorted({d.kind for d in declarations}, key=lambda k: _ORDER[k]):
            ordered.extend(
                _sorted_by_need([d for d in declarations if d.kind is layer], needs)
            )
        return ordered

    def _edges(
        self, declarations: list[_declarations.Declaration]
    ) -> dict[str, set[str]]:
        """Return the components each component is built from, by name.

        A census is left out: it is a live view of the session rather than a
        value one component takes from another, so it carries no order.
        """
        owners = _owners(declarations)
        owners.update({d.key: d for d in declarations})
        needs: dict[str, set[str]] = {d.name: set() for d in declarations}
        for declaration in declarations:
            params = _factories.injectable(declaration.cls, declaration.cfg_kwargs)
            for hint in params.values():
                target = owners.get(_factories.optional_arg(hint) or hint)
                if target is not None and target is not declaration:
                    needs[declaration.name].add(target.name)
        for question, askers in _factories.requirements(declarations).items():
            chosen = self._answers.get(question)
            if chosen is None:
                continue
            for asker in askers:
                if asker != chosen.name:
                    needs[asker].add(chosen.name)
        return needs

    def _check_layers(self, declarations: list[_declarations.Declaration]) -> None:
        """Refuse a component whose constructor reaches into a later layer.

        The layers are a build order, so an edge pointing forwards along it
        could only be satisfied by inverting that order. A census asks about
        the session rather than depending on it, and is left alone.

        Raises
        ------
        TypeError
            If a component depends on one built after it.
        """
        owners = _owners(declarations)
        for declaration in declarations:
            params = _factories.injectable(declaration.cls, declaration.cfg_kwargs)
            for pname, hint in params.items():
                target = owners.get(_factories.optional_arg(hint) or hint)
                if target is None:
                    continue
                _refuse_backwards(declaration, target, f"its {pname!r} parameter")

    def _answer(
        self, store: Store, declarations: list[_declarations.Declaration]
    ) -> None:
        """Answer each question a component asks about the session.

        One answer per question, not per component that asks. A census of the
        components is answered with a live view, because a component may be part
        of its own answer; one of the devices is answered with the mapping
        itself, since every device exists before any component is built.
        """
        for question, askers in _factories.requirements(declarations).items():
            key = key_for(question)
            if isinstance(question.marker, Devices):
                store.register_provider(
                    self._device_census(question.protocol), type_hint=key
                )
            elif isinstance(question.marker, (One, Maybe)):
                self._select(store, question, key, askers, declarations)
            else:
                store.register_provider(self._census(question.protocol), type_hint=key)

    def _census(self, protocol: type) -> Callable[[], Any]:
        def read() -> Any:
            return self.satisfying(protocol)

        return read

    def _device_census(self, protocol: type) -> Callable[[], Any]:
        def read() -> Any:
            return {
                name: device
                for name, device in self._devices.items()
                if _structural.satisfies(device, protocol)
            }

        return read

    def _select(
        self,
        store: Store,
        question: Question,
        key: Key,
        askers: list[str],
        declarations: list[_declarations.Declaration],
    ) -> None:
        """Bind the one component answering *question*, or refuse to build.

        Nothing exists yet, so the choice is made from the declared classes,
        and the answer reads the instance when something asks for it. Ordering
        puts the chosen component first, so by then there is one.
        `_verify_answers` confirms the choice once the instance is there.

        A question at most one component may answer, and none does, is left
        unregistered: its key is widened, so the store fills it with ``None``.
        """
        protocol = question.protocol
        matches = [d for d in declarations if _structural.satisfies(d.cls, protocol)]
        asks = f"{_listed(askers)} {'requires' if len(askers) == 1 else 'require'}"
        wanted = "exactly one" if isinstance(question.marker, One) else "at most one"
        if len(matches) > 1:
            raise TypeError(
                f"{asks} {wanted} component satisfying {protocol.__name__!r}, but "
                f"{len(matches)} do: {_listed([d.name for d in matches])}. Narrow "
                f"the protocol, or ask with 'Requires[{protocol.__name__}]' for "
                "all of them."
            )
        if not matches:
            self._answers[question] = None
            if isinstance(question.marker, One):
                raise TypeError(
                    f"{asks} exactly one component satisfying "
                    f"{protocol.__name__!r}, and the session holds none."
                    + _near_misses(declarations, protocol)
                )
            return
        chosen = matches[0]
        for asker in askers:
            origin = next(d for d in declarations if d.name == asker)
            _refuse_backwards(origin, chosen, f"the one {protocol.__name__!r}")
        if chosen.name in askers:
            raise TypeError(
                f"{chosen.name!r} asks for the one component satisfying "
                f"{protocol.__name__!r} and is the only one that does. A "
                "component cannot depend on itself; ask with "
                f"'Requires[{protocol.__name__}]', which may include the asker."
            )
        self._answers[question] = chosen
        store.register_provider(_built(chosen), type_hint=key)

    def _verify_components(self) -> None:
        """Check every built component against the protocol of its layer.

        A member assigned in ``__init__`` is invisible on the class, so a view
        answering ``placement`` from anything but a class attribute is only
        checkable now.
        """
        frontend = self.frontend
        for declaration in self._components():
            instance = declaration.instance
            if instance is None:
                continue
            view = declaration.kind is Layer.VIEW
            protocol: type = AttachableComponent if view else NamedComponent
            reasons = _structural.problems(instance, protocol)
            if reasons:
                raise TypeError(
                    f"{declaration.name!r} is declared as a "
                    f"{declaration.kind}, but does not satisfy "
                    f"{protocol.__name__!r}: " + "; ".join(reasons)
                )
            if view:
                frontend.check_placement(
                    instance, instance.placement, f"view {declaration.name!r}"
                )

    def _verify_answers(self) -> None:
        """Check every chosen component against the protocol it was chosen for.

        The choice is made before anything is built, so a member assigned in
        ``__init__`` is invisible then and can only be confirmed now.
        """
        for question, chosen in self._answers.items():
            if chosen is None or chosen.instance is None:
                continue
            reasons = _structural.problems(chosen.instance, question.protocol)
            if reasons:
                raise TypeError(
                    f"{chosen.name!r} was chosen as the one component satisfying "
                    f"{question.protocol.__name__!r}, but does not: "
                    + "; ".join(reasons)
                )

    def _is_unique(self, declaration: _declarations.Declaration) -> bool:
        others = [d for d in self._components() if d.cls is declaration.cls]
        if len(others) == 1:
            return True
        logger.debug(
            "%s is declared as %s; it can only be injected by name",
            declaration.cls.__name__,
            ", ".join(d.name for d in others),
        )
        return False

    def build_devices(self) -> None:
        """Construct the devices, which are built from no other component.

        They come before the store because a device is made from its own
        declaration and asks the session for nothing.
        """
        for declaration in self._declarations.values():
            if declaration.kind is not Layer.DEVICE:
                continue
            try:
                device = declaration.cls(declaration.name, **declaration.cfg_kwargs)
            except Exception as e:  # noqa: BLE001 - a missing device must not abort the app
                self._failed[declaration.name] = e
                logger.error("Failed to build device '%s': %s", declaration.name, e)
                continue
            self._devices[declaration.name] = device
            declaration.instance = device
            self._register_teardown(device)

    def _on_built(
        self, declaration: _declarations.Declaration, instance: NamedComponent
    ) -> None:
        declaration.instance = instance
        self._register_teardown(instance)

    def _register_teardown(self, component: object) -> None:
        """Hand the session's own teardown to the one owner of it.

        A component that declares ``shutdown`` is finalized without having to
        ask for it; one that does not needs no teardown at all.
        """
        shutdown = getattr(component, "shutdown", None)
        if not callable(shutdown):
            return
        if not inspect.iscoroutinefunction(shutdown):
            self.on_release(shutdown)
            return

        def close() -> None:
            run_coro(shutdown())

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
            _factories.optional_arg(hint) or hint
            for declaration in declarations
            for hint in _factories.injectable(
                declaration.cls, declaration.cfg_kwargs
            ).values()
        }
        used = self._used(declarations, wanted)
        for declaration in declarations:
            provided = _provides.shared(declaration.cls)
            for method, key in provided.items():
                if key not in wanted:
                    logger.warning(
                        "%s.%s shares %r, which no component asks for",
                        declaration.name,
                        method,
                        getattr(key, "__name__", key),
                    )
            requires = _factories.injectable(declaration.cls, declaration.cfg_kwargs)
            if not provided and not requires and declaration.name not in used:
                logger.warning(
                    "%r shares nothing, asks for nothing and is wired to nothing; "
                    "it is built and reachable, and does nothing",
                    declaration.name,
                )

    def _used(
        self, declarations: list[_declarations.Declaration], wanted: set[Any]
    ) -> set[str]:
        """Check the components something in the session reaches.

        *wanted* is every type a constructor asks for, so a component another
        one is built from counts, by its key or by its class.
        """
        names = {c.publisher for c in self.connections}
        names |= {c.consumer for c in self.connections}
        names |= {s.consumer for s in self.subscriptions}
        names |= {
            chosen.name for chosen in self._answers.values() if chosen is not None
        }
        names |= {
            declaration.name
            for declaration in declarations
            if declaration.key in wanted or declaration.cls in wanted
        }
        for question in _factories.requirements(declarations):
            names |= {
                declaration.name
                for declaration in declarations
                if _structural.satisfies(declaration.cls, question.protocol)
            }
        return names


def _unanswered(store: Store, params: Mapping[str, Any]) -> list[tuple[str, object]]:
    """Return the parameters of *params* nothing in the store answers.

    Everything a component may be built from is registered by the time it is
    reached, so a parameter with no provider has none coming.
    """
    return [
        (pname, hint)
        for pname, hint in params.items()
        if _factories.optional_arg(hint) is None
        and next(store.iter_providers(hint), None) is None
    ]


def _unanswered_message(name: str, unanswered: list[tuple[str, object]]) -> str:
    """Return the refusal naming what *name* asked for and did not get."""
    named = _listed_plain(
        [f"{pname!r} ({getattr(hint, '__name__', hint)})" for pname, hint in unanswered]
    )
    return (
        f"{name!r} asks for {named}, which nothing in the session provides. "
        "A component names the values it needs, and the session is not one of "
        "them."
    )


def _refuse_unanswered(store: Store, name: str, params: Mapping[str, Any]) -> None:
    """Refuse *name* asking for something the session does not hold.

    Raises
    ------
    TypeError
        Naming the parameters and the types nothing answers.
    """
    unanswered = _unanswered(store, params)
    if unanswered:
        raise TypeError(_unanswered_message(name, unanswered))


def _listed_plain(items: list[str]) -> str:
    if len(items) < 2:
        return items[0] if items else "nothing"
    return f"{', '.join(items[:-1])} and {items[-1]}"


def _constant(value: Any) -> Callable[[], Any]:
    """Return a callable answering with *value*."""

    def read() -> Any:
        return value

    return read


def _built(declaration: _declarations.Declaration) -> Callable[[], Any]:
    """Return a callable answering with what *declaration* was built into."""

    def read() -> Any:
        return declaration.instance

    return read


def _sorted_by_need(
    group: list[_declarations.Declaration], needs: Mapping[str, set[str]]
) -> list[_declarations.Declaration]:
    """Return *group* with each component after the ones it is built from.

    Only edges inside *group* matter: anything in an earlier layer is already
    built. Ties keep declaration order, so a session that states no dependency
    builds in the order it is written.

    Raises
    ------
    TypeError
        If two components of one layer are built from each other.
    """
    names = {d.name for d in group}
    pending = {d.name: {n for n in needs[d.name] if n in names} for d in group}
    ordered: list[_declarations.Declaration] = []
    remaining = list(group)
    while remaining:
        ready = [d for d in remaining if not pending[d.name]]
        if not ready:
            named = _listed(sorted(d.name for d in remaining))
            raise TypeError(
                f"{named} are built from each other, so none of them can be "
                "built first. Break the cycle, or share the value one way only."
            )
        for declaration in ready:
            ordered.append(declaration)
            for other in pending.values():
                other.discard(declaration.name)
        remaining = [d for d in remaining if d not in ready]
    return ordered


def _owners(
    declarations: list[_declarations.Declaration],
) -> dict[Any, _declarations.Declaration]:
    """Return every type naming a component, by the declaration answering it.

    A class declared twice is left out: nothing can be injected by it, so no
    edge can name it.
    """
    counts: dict[type, int] = {}
    for declaration in declarations:
        counts[declaration.cls] = counts.get(declaration.cls, 0) + 1
    found: dict[Any, _declarations.Declaration] = {}
    for declaration in declarations:
        if counts[declaration.cls] == 1:
            found[declaration.cls] = declaration
        for provided in _provides.shared(declaration.cls).values():
            found[provided] = declaration
    return found


def _refuse_backwards(
    asker: _declarations.Declaration,
    target: _declarations.Declaration,
    where: str,
) -> None:
    """Refuse *asker* depending on *target*, when *target* is built later."""
    if _ORDER[target.kind] <= _ORDER[asker.kind]:
        return
    raise TypeError(
        f"{asker.name!r} is a {asker.kind} and {where} asks for "
        f"{target.name!r}, which is a {target.kind}. A {asker.kind} is built "
        f"before a {target.kind}, so it cannot depend on one; share the value "
        "the other way, or move what they both need into an earlier layer."
    )


def _listed(names: list[str]) -> str:
    quoted = [repr(name) for name in names]
    if len(quoted) < 2:
        return quoted[0] if quoted else "nothing"
    return f"{', '.join(quoted[:-1])} and {quoted[-1]}"


def _near_misses(declarations: list[_declarations.Declaration], protocol: type) -> str:
    """Report the declared classes that carry some of *protocol*, and why not all."""
    wanted = _structural.members(protocol)
    lines = [
        f"\n  {declaration.name!r}: "
        + "; ".join(_structural.problems(declaration.cls, protocol))
        for declaration in declarations
        if any(hasattr(declaration.cls, member) for member in wanted)
        and _structural.problems(declaration.cls, protocol)
    ]
    return "".join(lines)


def _base_for(cls: type[Session], frontend: object) -> type[Session]:
    """Return the class a session naming *frontend* is built on.

    A session class already built against that toolkit is kept, so a subclass
    carrying its own declarations stays the one instantiated.
    """
    if frontend is None:
        return cls
    dotted = _FRONTENDS.get(str(frontend))
    if dotted is None:
        raise ValueError(
            f"the configuration names frontend {frontend!r}, which no session "
            f"is built against. Known: {', '.join(sorted(_FRONTENDS))}."
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


def _instantiate(declaration: _declarations.HookDeclaration, owner: str) -> object:
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
