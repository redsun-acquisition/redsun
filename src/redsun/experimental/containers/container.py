from __future__ import annotations

import asyncio
import inspect
import logging

# resolved at runtime: a container subclass inherits the annotations below,
# and get_type_hints evaluates them against this module's globals
from collections.abc import Mapping  # noqa: TC003
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Final, Self, cast

import yaml
from dishka import AnyOf, Provider, Scope, make_container

# runtime import: the annotations below are evaluated by the graph
from ophyd_async.core import Device  # noqa: TC002

from redsun.aio import run_coro
from redsun.experimental.containers import (
    _declarations,
    _factories,
    _plugins,
    _structural,
)
from redsun.experimental.containers._declarations import Layer
from redsun.experimental.containers._frontend import Frontend, check_placement
from redsun.experimental.virtual import _provides
from redsun.experimental.virtual._container import VirtualContainer
from redsun.experimental.virtual._protocols import PPresenter, PView
from redsun.experimental.virtual._requires import Devices, Maybe, One, key_for

if TYPE_CHECKING:
    from collections.abc import Callable

    from dishka import Container
    from psygnal import SignalInstance

    from redsun.experimental.containers._declarations import Key
    from redsun.experimental.virtual._requires import Question
    from redsun.experimental.virtual._wiring import Connection, SlotThread

__all__ = ["AppContainer"]

logger = logging.getLogger("redsun")

_ORDER: Final[dict[Layer, int]] = {Layer.DEVICE: 0, Layer.PRESENTER: 1, Layer.VIEW: 2}
"""The order the layers are built in, which is the order they may depend in."""

_FRONTENDS: Final[dict[str, str]] = {
    "pyqt": "redsun.experimental.containers.qt:QtAppContainer",
    "pyside": "redsun.experimental.containers.qt:QtAppContainer",
}
"""The container a session builds on, by the name its configuration gives."""


class AppContainer:
    """Application container whose components are declared as annotations.

    ```python
    class MyApp(QtAppContainer):
        __slots__ = ()

        config = "session.yaml"

        stage: AsDevice[MyStage]
        motor_ctrl: AsPresenter[MotorPresenter]
        motor_widget: Annotated[AsView[MotorView], Declare(step_size=5.0)]

        def wire(self) -> None:
            self.connect(self.motor_ctrl.sig_moved, self.motor_widget.update)
    ```

    An annotation is a declaration only if it names a layer, so a container may
    hold ordinary attributes alongside its components. The attribute name is
    both the component name and its configuration key; `Alias` and `FromConfig`
    override each. Reading a declared attribute on a built container gives the
    instance, typed by its annotation.

    Declarations are annotations, so they claim no slot and no class
    attribute; a subclass adding ``__slots__ = ()`` keeps its instances free
    of a ``__dict__``.
    """

    __slots__ = (
        "_answers",
        "_config",
        "_declarations",
        "_devices",
        "_di",
        "_is_built",
        "_virtual",
    )

    config: ClassVar[str | Path | Mapping[str, Any] | None] = None
    providers: ClassVar[list[Provider]] = []
    frontend: ClassVar[type[Frontend]] = Frontend
    """The toolkit this container is built against.

    Set by subclassing, as `redsun.experimental.containers.qt.QtAppContainer` does. The
    default attaches nothing and constrains no view.
    """

    def __init__(self, config: str | Path | Mapping[str, Any] | None = None) -> None:
        """Prepare an empty container, to be filled by `build`.

        *config* is the session configuration, overriding the class attribute
        of the same name for this instance alone.
        """
        self._config = config
        self._virtual = VirtualContainer()
        self._di: Container | None = None
        self._declarations: dict[str, _declarations.Declaration] = {}
        self._devices: dict[str, Device] = {}
        self._answers: dict[Question, _declarations.Declaration | None] = {}
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
    def from_config(cls, source: str | Path | Mapping[str, Any]) -> Self:
        """Return a container for a session described entirely by *source*.

        Every component the configuration names is declared, its layer coming
        from the section it appears under, so a session needs no container
        class of its own. The ``frontend`` key chooses the container to build
        on; naming none builds on this one, which is what a session with no
        toolkit wants.

        The container comes back unbuilt, so that whatever the configuration
        cannot say is still said in Python before `build` runs.

        Raises
        ------
        ValueError
            If the configuration names a frontend no container is built
            against.
        TypeError
            If it names one this container is not built against.
        """
        config = _read_config(source)
        return cast("Self", _base_for(cls, config.get("frontend"))(config))

    @property
    def devices(self) -> Mapping[str, Device]:
        """The devices that built successfully."""
        return dict(self._devices)

    @property
    def presenters(self) -> Mapping[str, PPresenter]:
        """The presenters that built successfully."""
        return self._built(Layer.PRESENTER)

    @property
    def views(self) -> Mapping[str, PView]:
        """The views that built successfully, ready for a frontend to attach."""
        return self._built(Layer.VIEW)

    @property
    def declarations(self) -> Mapping[str, _declarations.Declaration]:
        """The declarations collected from the class."""
        return dict(self._declarations)

    @property
    def virtual_container(self) -> VirtualContainer:
        """The data exchange layer shared by every component."""
        return self._virtual

    @property
    def is_built(self) -> bool:
        """Whether `build` has completed."""
        return self._is_built

    def build(self) -> Self:
        """Instantiate the application.

        Devices are built directly rather than through the graph, so that one
        which fails is logged and skipped; a graph edge could not be. The
        components come out of a single scope, ordered only by what they
        depend on.
        """
        if self._is_built:
            logger.warning("Container already built, skipping rebuild")
            return self

        config = _read_config(self.config if self._config is None else self._config)
        self._virtual._set_configuration(config)
        self._declarations = _declarations.read(type(self), config, self.frontend)
        self._build_devices()

        framework = self._virtual.provider(lambda: dict(self._devices))
        providers = [framework, *self.providers, *_plugins.load_providers(config)]
        components = self._component_provider()

        self._di = make_container(components, *providers)
        # first registered, so last run: a provider's own finalizers close
        # after every component that may still be using them
        self._virtual.on_release(self._di.close)
        self._resolve(self._di)
        self._verify_components()
        self._verify_answers()

        self._virtual._set_components(
            {
                declaration.name: declaration.instance
                for declaration in self._components()
                if declaration.instance is not None
            }
        )
        self._virtual._seal()
        self.wire()
        self._apply_wiring_config(config)
        self._is_built = True
        logger.info(
            "Container built: %d devices, %d presenters, %d views",
            len(self._devices),
            sum(1 for d in self._components() if d.kind is Layer.PRESENTER),
            sum(1 for d in self._components() if d.kind is Layer.VIEW),
        )
        return self

    def wire(self) -> None:
        """Connect the signals and slots of built components.

        Every component exists by the time this runs. Connects nothing by
        default.
        """

    def connect(
        self,
        signal: SignalInstance,
        slot: Callable[..., Any],
        *,
        thread: SlotThread = None,
    ) -> Connection:
        """Connect a signal to a slot, recording the link for teardown."""
        return self._virtual.connect(signal, slot, thread=thread)

    def connect_devices(self, mock: bool = False) -> None:
        """Connect every built device through ophyd-async.

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
        """Tear the application down.

        One owner does all of it: connections, the ``shutdown`` method of
        every component that has one, and the dependency graph itself, in
        reverse build order.
        """
        if not self._is_built:
            return
        self._is_built = False
        self._virtual.release()
        logger.info("Container shutdown complete")

    def _built(self, layer: Layer) -> dict[str, Any]:
        return {
            d.name: d.instance
            for d in self._declarations.values()
            if d.kind is layer and d.instance is not None
        }

    def _components(self) -> list[_declarations.Declaration]:
        return [d for d in self._declarations.values() if d.kind is not Layer.DEVICE]

    def _component_provider(self) -> Provider:
        declarations = self._components()
        provider = Provider(scope=Scope.APP)
        shared: dict[Key, str] = {}
        for declaration in declarations:
            provider.provide(
                _factories.factory(declaration, self._on_built),
                provides=(
                    AnyOf[declaration.key, declaration.cls]
                    if self._is_unique(declaration)
                    else declaration.key
                ),
            )
            _provides.register(provider, declaration, shared)

        self._check_layers(declarations)
        _factories.register_optionals(provider, declarations)
        self._register_requirements(provider, declarations)
        return provider

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

    def _register_requirements(
        self, provider: Provider, declarations: list[_declarations.Declaration]
    ) -> None:
        """Answer each question a component asks about the session.

        One answer per question, not per component that asks. A census of the
        components is answered with a live view, because a component may be part
        of its own answer; one of the devices is answered with the mapping
        itself, since every device exists before any component is built. A
        question expecting a single component is answered with an edge to that
        component, so it is built first.
        """
        for question, askers in _factories.requirements(declarations).items():
            key = key_for(question)
            if isinstance(question.marker, Devices):
                provider.provide(self._device_census(question.protocol, key))
            elif isinstance(question.marker, (One, Maybe)):
                self._select(provider, question, key, askers, declarations)
            else:
                provider.provide(self._census(question.protocol, key))

    def _census(self, protocol: type, key: Key) -> Callable[..., Any]:
        # the protocol is closed over rather than carried as a default
        # argument, which would leak into the signature dishka inspects
        def build(**_: Any) -> Any:
            return self._virtual.satisfying(protocol)

        return _factories.synthesize(build, {}, key, f"every_{protocol.__name__}")

    def _device_census(self, protocol: type, key: Key) -> Callable[..., Any]:
        def build(**_: Any) -> Any:
            return {
                name: device
                for name, device in self._devices.items()
                if _structural.satisfies(device, protocol)
            }

        return _factories.synthesize(build, {}, key, f"devices_of_{protocol.__name__}")

    def _select(
        self,
        provider: Provider,
        question: Question,
        key: Key,
        askers: list[str],
        declarations: list[_declarations.Declaration],
    ) -> None:
        """Bind the one component answering *question*, or refuse to build.

        Nothing exists yet, so the choice is made from the declared classes.
        `_verify_answers` confirms it once the instance is there.
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
            provider.provide(_factories.absent(key, protocol.__name__))
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
        provider.alias(source=chosen.key, provides=key)

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
            protocol: type = PView if view else PPresenter
            reasons = _structural.problems(instance, protocol)
            if reasons:
                raise TypeError(
                    f"{declaration.name!r} is declared as a "
                    f"{declaration.kind}, but does not satisfy "
                    f"{protocol.__name__!r}: " + "; ".join(reasons)
                )
            if view:
                check_placement(
                    instance.placement, frontend, f"view {declaration.name!r}"
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

    def _build_devices(self) -> None:
        for declaration in self._declarations.values():
            if declaration.kind is not Layer.DEVICE:
                continue
            try:
                device = declaration.cls(declaration.name, **declaration.cfg_kwargs)
            except Exception as e:  # noqa: BLE001 - a missing device must not abort the app
                logger.error("Failed to build device '%s': %s", declaration.name, e)
                continue
            self._devices[declaration.name] = device
            declaration.instance = device
            self._register_teardown(device)

    def _resolve(self, scope: Container) -> None:
        for declaration in self._components():
            scope.get(declaration.key)

    def _on_built(self, declaration: _declarations.Declaration, instance: Any) -> None:
        declaration.instance = instance
        self._virtual.register_signals(instance, name=declaration.name)
        self._register_teardown(instance)

    def _register_teardown(self, component: object) -> None:
        """Hand the container's own teardown to the one owner of it.

        A component that declares ``shutdown`` is finalized without having to
        ask for it; one that does not needs no teardown at all.
        """
        shutdown = getattr(component, "shutdown", None)
        if not callable(shutdown):
            return
        if not inspect.iscoroutinefunction(shutdown):
            self._virtual.on_release(shutdown)
            return

        def close() -> None:
            run_coro(shutdown())

        self._virtual.on_release(close)

    def _apply_wiring_config(self, config: Mapping[str, Any]) -> None:
        for rule in config.get("wiring", []):
            self._virtual.connect_paths(rule["from"], rule["to"])


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


def _base_for(cls: type[AppContainer], frontend: object) -> type[AppContainer]:
    """Return the container a session naming *frontend* is built on.

    A container already built against that toolkit is kept, so a subclass
    carrying its own declarations stays the one instantiated.
    """
    if frontend is None:
        return cls
    dotted = _FRONTENDS.get(str(frontend))
    if dotted is None:
        raise ValueError(
            f"the configuration names frontend {frontend!r}, which no container "
            f"is built against. Known: {', '.join(sorted(_FRONTENDS))}."
        )
    module_name, _, class_name = dotted.partition(":")
    resolved: type[AppContainer] = getattr(import_module(module_name), class_name)
    if issubclass(cls, resolved):
        return cls
    if cls is not AppContainer:
        raise TypeError(
            f"the configuration names frontend {frontend!r}, which builds on "
            f"{resolved.__name__}, but from_config was called on "
            f"{cls.__name__}, which is not one of those."
        )
    return resolved


def _read_config(source: str | Path | Mapping[str, Any] | None) -> Mapping[str, Any]:
    if source is None:
        return {}
    if isinstance(source, (str, Path)):
        with open(source) as fh:
            loaded = yaml.safe_load(fh)
        return dict(loaded or {})
    return source
