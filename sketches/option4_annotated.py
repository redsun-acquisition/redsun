# ruff: noqa
"""Option 4: declarations as Annotated class annotations, ophyd-async style.

Not a fourth DI backend. This is Option 1's runtime with a different
declaration syntax, so it composes with the container layer in
`container_layer.py` rather than replacing it.

ophyd-async already declares device children this way:

    class Sensor(StandardReadable, EpicsDevice):
        value: Annotated[SignalR[float], PvSuffix("Value"), Format.HINTED_SIGNAL]
        mode:  Annotated[SignalRW[Mode], PvSuffix("Mode"), Format.CONFIG_SIGNAL]

The annotation carries the type; the metadata carries the wiring instructions;
a connector walks `get_type_hints(cls, include_extras=True)` at init. An
author who already reads ophyd-async device code recognises the shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated, Any, Generic, TypeVar, get_args, get_type_hints

from dishka import FromComponent, Provider, Scope, provide

from redsun.presenter import Presenter
from redsun.storage import SessionPathProvider
from redsun.view.qt import QtView
from redsun.virtual import VirtualContainer

A = Annotated


@dataclass
class Declare:
    """Inline keyword arguments for a declared component."""

    kwargs: dict[str, Any] = field(default_factory=dict)

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


@dataclass
class FromConfig:
    """Read further keyword arguments from a section of the config file."""

    section: str


@dataclass
class Alias:
    """Component name, overriding the attribute name."""

    name: str


class Frontend: ...


class Qt(Frontend): ...


class Web(Frontend): ...


FE = TypeVar("FE", bound=Frontend)


class AppContainer(Generic[FE]):
    """Declarations are read from annotations, not from class attribute values.

    `__init_subclass__` walks `get_type_hints(cls, include_extras=True)`, takes
    every hint whose metadata contains a Declare/FromConfig/Alias, and builds
    the same `_Declaration` objects `container_layer.py` consumes. The kind
    (device, presenter, view) is inferred from the annotated class, which is
    available *before* instantiation.

    `__getattr__` returns the built instance. Because the attribute is only
    annotated and never assigned, there is no descriptor and no cast: mypy
    reads the annotation directly, so `self.paths_ctrl` is a StoragePresenter
    for the same reason any annotated attribute is what it says it is.
    """

    def __init_subclass__(cls, config: str | None = None, **kw: Any) -> None:
        super().__init_subclass__(**kw)
        hints = get_type_hints(cls, include_extras=True)
        for attr, hint in hints.items():
            target, *metadata = get_args(hint) or (hint,)
            if not any(isinstance(m, (Declare, FromConfig, Alias)) for m in metadata):
                continue
            ...  # -> _Declaration(target, name, kind, cfg_kwargs)

        # the frontend type argument is available at runtime, via __orig_bases__
        cls._frontend = _type_arg(cls)

    def __getattr__(self, name: str) -> Any:
        try:
            return self._declarations[name].instance
        except KeyError:
            raise AttributeError(name) from None


def _type_arg(cls: type) -> type | None:
    """The concrete FE in `class MyApp(AppContainer[Qt])`."""
    for base in getattr(cls, "__orig_bases__", ()):
        args = get_args(base)
        if args:
            return args[0]
    return None


class Services(Provider):
    scope = Scope.APP

    @provide
    def paths(self, bus: VirtualContainer) -> SessionPathProvider:
        return SessionPathProvider(session=bus.session)


class StoragePresenter(Presenter):
    def __init__(self, name: str, /, paths: SessionPathProvider, max_digits: int = 5):
        super().__init__(name)


class MotorPresenter(Presenter):
    def __init__(self, name: str, /, bus: VirtualContainer, axis: str = "X"):
        super().__init__(name)


class StorageView(QtView):
    def __init__(
        self,
        name: str,
        /,
        bus: VirtualContainer,
        paths: SessionPathProvider | None = None,
    ) -> None:
        super().__init__(name)


class MyApp(AppContainer[Qt], config="config.yaml"):
    providers = [Services()]

    paths_ctrl: A[StoragePresenter, Declare(max_digits=6)]
    motor_x: A[MotorPresenter, Declare(axis="X")]
    motor_y: A[MotorPresenter, Declare(axis="Y"), Alias("motor_vertical")]
    storage_ui: A[StorageView, FromConfig("storage")]

    def wire(self) -> None:
        # self.paths_ctrl is StoragePresenter because the annotation says so,
        # not because a cast in declare_presenter claimed it
        self.connect(self.paths_ctrl.sig_plan_set, self.storage_ui.update_base_dir)


# Where this is better than declare_*()
# -------------------------------------
# 1. The typing stops being a lie. declare_presenter is
#    `cast("T", _PresenterField(...))`: it claims to return a StoragePresenter
#    and returns a sentinel, then __init_subclass__ swaps in a descriptor whose
#    __get__ returns Any. With an annotation, the declared type *is* the type.
# 2. One declaration form instead of three. The kind follows from the annotated
#    class, checked before anything is instantiated, which is where the
#    class-level half of the dual gate wants to live anyway.
# 3. Metadata composes. dishka's own Annotated markers sit in the same slot:
#
#        engine: A[Engine, FromComponent("acquisition")]
#
#    so component isolation, if it is ever wanted, needs no new syntax.
# 4. Ordering is free. Annotations preserve declaration order and, unlike
#    assigned values, cannot be shadowed by an inherited attribute of the same
#    name without the subclass saying so.
#
# What it costs
# -------------
# 1. `from __future__ import annotations` is mandatory in this repo, so every
#    hint is a string and `get_type_hints` must resolve it against the defining
#    module's globals. A component class defined inside a test function is not
#    in those globals and raises NameError. Today's `declare_presenter(cls)`
#    holds the class object and never has this problem. This is the real cost
#    and it lands squarely on tests/container/.
# 2. No value means no `__set_name__`, so the alias has to move into metadata
#    (above) rather than being a keyword argument.
# 3. `__getattr__` is untyped at runtime; mypy is satisfied by the annotation
#    but a typo in a name string elsewhere is no longer caught by attribute
#    access.
#
# On __class_getitem__
# --------------------
# It buys one real thing and not the thing the original sketch wanted.
#
# It buys: the type argument in `class MyApp(AppContainer[Qt])` is readable at
# runtime from __orig_bases__, so the container can reject a Qt-only view in a
# Web app at build time, and _FRONTEND_CONTAINERS (the dotted-path string dict
# in container.py) can be replaced by the type argument itself.
#
# On propagating a dependency parameter into the declarations
# -----------------------------------------------------------
# This does work, contrary to what I first said. Verified with mypy --strict
# in genprobe.py / genprobe2.py / genprobe3.py; run them to see for yourself.
#
#     class GenericApp(AppContainer[D], Generic[D]):
#         p: A[MyPresenter[D], Declare(max_digits=6)]
#
#     class MyApp(GenericApp[ConcreteDep]): ...
#
#     reveal_type(MyApp().p)          # MyPresenter[ConcreteDep]
#     bad: GenericApp[NotADep]        # error: not a subtype of Dependency
#
# The bound on D is what gives the static "this application supplies what its
# presenters demand" gate. It is enforced at the point the app is
# parameterized, which is where you wanted it.
#
# Two conditions, and one of them is why the original sketch could not work:
#
# 1. The root must be generic. `Root[D]` with `dependency: D`, not a dataclass
#    whose member is annotated with the concrete `Dependency`. There is no
#    member projection in Python's type system: you cannot write "the D that
#    is the type of RD.dependency". This is the single hard impossibility.
# 2. One type parameter per dependency that varies. Root2[D, D2] with
#    Generic[D, D2] works and keeps each presenter matched to its own
#    parameter, but a single RD standing for a heterogeneous root does not
#    project.
#
# The annotation is load-bearing: `p = declare_presenter(MyPresenter)` infers
# MyPresenter[Any], because inference does not pick the parameter up from the
# passed class. The parameter has to appear in an annotation, either on a
# descriptor field or annotation-only as above. That is the strongest argument
# for this syntax: the thing generics require is the thing this form makes
# mandatory anyway.
#
# `__getattr__` does not interfere. mypy prefers the class-body annotation and
# only falls through to `__getattr__` for names that were never declared.
#
# What __class_getitem__ separately buys: the type argument in
# `class MyApp(AppContainer[Qt])` is readable at runtime from __orig_bases__,
# so the container can reject a Qt-only view in a Web app at build time, and
# _FRONTEND_CONTAINERS (the dotted-path string dict in container.py) can be
# replaced by the type argument itself.
