"""Tests for the session."""

from __future__ import annotations

import gc
import logging
import weakref
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated, Any, ClassVar, NewType, cast

import pydantic
import pytest
from mock_bundle.devices import MockStage
from mock_bundle.presenters import MockLatePresenter, MockRegistrar
from ophyd_async.core import (
    Device,
)
from psygnal import Signal

from redsun import (
    Alias,
    AsDevice,
    AsPresenter,
    AsView,
    BuildableSession,
    BuildError,
    CallbackType,
    ConfigurationError,
    Declare,
    DeviceMapping,
    FromConfig,
    Frontend,
    Placement,
    Session,
    SessionConfig,
    provides,
    slot,
)
from redsun.aio import run_coro
from redsun.ports import WiringError
from redsun.session import Layer

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from redsun import Link
    from redsun.testing import BuildSession


Readings = NewType("Readings", "dict[str, float]")


Descriptions = NewType("Descriptions", "dict[str, str]")


Missing = NewType("Missing", "dict[str, int]")


class FailsOnce:
    """Presenter that cannot be made the first time, and can afterwards."""

    def __init__(self, name: str, attempts: list[str]) -> None:
        self.name = name
        attempts.append(name)
        if len(attempts) == 1:
            raise ValueError("not yet")


class WorksOnce(MockStage):  # type: ignore[misc]
    """Device that can be made the first time, and not afterwards."""

    def __init__(self, name: str, attempts: list[str]) -> None:
        attempts.append(name)
        if len(attempts) > 1:
            raise ValueError("no longer")
        super().__init__(name)


class Ctrl:
    """Presenter sharing two values derived from its devices."""

    sig_moved = Signal(str)

    def __init__(self, name: str, *, devices: DeviceMapping, gain: float = 1.0) -> None:
        self.name = name
        self.devices = devices
        self.gain = gain

    @provides
    def readings(self) -> Readings:
        return Readings({name: self.gain for name in self.devices})

    @provides
    def descriptions(self) -> Descriptions:
        return Descriptions(
            {
                name: type(d).__name__
                for name in self.devices
                for d in [self.devices[name]]
            }
        )

    @slot
    def on_move(self, where: str) -> None:
        self.moved = where


@dataclass(frozen=True)
class Panel(Placement):
    """A placement the toy frontend below attaches."""

    side: str


@dataclass(frozen=True)
class Elsewhere(Placement):
    """A placement no frontend attaches."""


class Attachable:
    """The type Toy demands of a view, standing in for a toolkit class."""


class Attached(Attachable):
    """A view Toy can attach."""

    placement: Placement = Panel("left")

    def __init__(self, name: str) -> None:
        self.name = name


class Unattachable:
    """A view asking for a placement Toy attaches, without being what it demands."""

    placement: Placement = Panel("left")

    def __init__(self, name: str) -> None:
        self.name = name


class Toy(Frontend):
    """A frontend that attaches one placement, standing in for a real one."""

    requires: ClassVar[Mapping[type[Placement], type]] = {Panel: Attachable}


class Widget:
    """View consuming one required and one optional shared value."""

    placement: Placement = Panel("left")

    def __init__(
        self,
        name: str,
        *,
        label: str = "",
    ) -> None:
        self.name = name
        self.callbacks: Mapping[str, CallbackType] = {}
        self.readings: Readings | None = None
        self.missing: Missing | None = None
        self.label = label

    def setup(
        self,
        callbacks: Mapping[str, CallbackType],
        readings: Readings,
        missing: Missing | None = None,
    ) -> None:
        self.callbacks = callbacks
        self.readings = readings
        self.missing = missing

    @slot
    def refresh(self, where: str) -> None:
        self.seen = where


class Registrar(MockRegistrar):  # type: ignore[misc]
    """Document router presenter that records being shut down."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.closed = False

    def shutdown(self) -> None:
        self.closed = True


class Tunable:
    """Presenter with a defaulted parameter and a defaulted `setup` value."""

    def __init__(self, name: str, *, step: float = 1.5) -> None:
        self.name = name
        self.step = step
        self.readings: Readings | None = None

    def setup(self, readings: Readings | None = None) -> None:
        self.readings = readings


class Dependency:
    """Presenter that `Dependent` takes in its `setup`."""

    def __init__(self, name: str) -> None:
        self.name = name


class Dependent:
    """Presenter taking `Dependency` once every component exists."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.other: Dependency | None = None

    def setup(self, other: Dependency) -> None:
        self.other = other


class ClosingRecorder:
    """Presenter nothing depends on, noting its shutdown."""

    def __init__(self, name: str, teardowns: list[str]) -> None:
        self.name = name
        self.teardowns = teardowns

    def shutdown(self) -> None:
        self.teardowns.append(self.name)


class ClosingDependent:
    """Presenter taking `ClosingRecorder` once every component exists, noting its shutdown."""

    def __init__(self, name: str, teardowns: list[str]) -> None:
        self.name = name
        self.teardowns = teardowns
        self.other: ClosingRecorder | None = None

    def setup(self, other: ClosingRecorder) -> None:
        self.other = other

    def shutdown(self) -> None:
        self.teardowns.append(self.name)


class Idle:
    """Presenter that shares nothing, asks for nothing and is wired to nothing."""

    def __init__(self, name: str) -> None:
        self.name = name


class OrderedApp(Session):
    second: Annotated[AsPresenter[ClosingDependent], Alias("second")]
    first: Annotated[AsPresenter[ClosingRecorder], Alias("first")]


class App(Session):
    config: ClassVar[Mapping[str, Any]] = {
        "session": "test-session",
        "devices": {"stage": {"axis": "Z"}},
        "presenters": {"ctrl": {"gain": 2.0}},
        "views": {"widget": {"label": "from-config"}},
    }

    motor: Annotated[AsDevice[MockStage], FromConfig("stage")]
    ctrl: AsPresenter[Ctrl]
    registrar: AsPresenter[Registrar]
    late: AsPresenter[MockLatePresenter]
    tunable: AsPresenter[Tunable]
    widget: Annotated[AsView[Widget], Declare(label="inline")]


class Nameless:
    """Presenter taking the name the framework hands it and dropping it."""

    def __init__(self, name: str) -> None:
        self.gain = 1.0


class NamelessView(Nameless, Attachable):
    """View doing the same, reached through the placement half of the protocol."""

    placement: Placement = Panel("left")


class NamelessApp(Session):
    ctrl: AsPresenter[Nameless]


class NamelessViewApp(Session):
    frontend = Toy
    panel: AsView[NamelessView]


class Deferred:
    """View answering its placement from a property rather than the class."""

    def __init__(self, name: str) -> None:
        self.name = name

    @property
    def placement(self) -> Placement:
        return Elsewhere()


class DeferredApp(Session):
    frontend = Toy

    stray: AsView[Deferred]


@pytest.fixture
def app() -> Any:
    container = App().build()
    yield container
    container.shutdown()


class WantsTheSession:
    def __init__(self, name: str, *, session: Session) -> None:
        self.name = name
        self.session = session


class LocatorApp(Session):
    greedy: AsPresenter[WantsTheSession]


class Duplicated:
    def __init__(self, name: str) -> None:
        self.name = name

    @provides
    def value(self) -> Readings:
        return Readings({})


class TwoOwners(Session):
    first: Annotated[AsPresenter[Duplicated], Alias("first")]
    second: Annotated[AsPresenter[Duplicated], Alias("second")]


ViewerModel = NewType("ViewerModel", "dict[str, str]")


class Displaying:
    """A view owning something another view of the same layer wants."""

    placement: Placement = Panel("left")

    def __init__(self, name: str) -> None:
        self.name = name
        self._viewer = ViewerModel({})

    @provides
    def viewer(self) -> ViewerModel:
        return self._viewer


class Controlling:
    """A view reaching for what a view built beside it owns."""

    placement: Placement = Panel("left")

    def __init__(self, name: str) -> None:
        self.name = name
        self.viewer: ViewerModel | None = None

    def setup(self, viewer: ViewerModel) -> None:
        self.viewer = viewer


class WatchingAView:
    """A presenter naming the class of a view."""

    def __init__(self, name: str) -> None:
        self.name = name

    def setup(self, display: Displaying) -> None:
        self.display = display


class WantingWhatAViewOwns:
    """A presenter asking for a type only a view shares."""

    def __init__(self, name: str) -> None:
        self.name = name

    def setup(self, viewer: ViewerModel) -> None: ...


class HoldingAPresenter:
    """A view naming the class of a presenter, which is the allowed direction."""

    placement: Placement = Panel("left")

    def __init__(self, name: str) -> None:
        self.name = name
        self.ctrl: Dependency | None = None

    def setup(self, ctrl: Dependency) -> None:
        self.ctrl = ctrl


class SameLayerApp(Session):
    display: AsView[Displaying]
    control: AsView[Controlling]


class PresenterOnAViewClass(Session):
    watcher: AsPresenter[WatchingAView]
    display: AsView[Displaying]


class PresenterOnAViewValue(Session):
    wanting: AsPresenter[WantingWhatAViewOwns]
    display: AsView[Displaying]


class ViewOnAPresenter(Session):
    recorder: AsPresenter[Dependency]
    holder: AsView[HoldingAPresenter]


class TakingAComponent:
    """A presenter naming another component's class in its constructor."""

    def __init__(self, name: str, *, other: Dependency) -> None:
        self.name = name
        self.other = other


class TakingASharedValue:
    """A presenter asking for what another component shares, too early."""

    def __init__(self, name: str, *, viewer: ViewerModel) -> None:
        self.name = name
        self.viewer = viewer


class TakingTheCatalogue:
    """A presenter asking for the callback catalogue in its constructor."""

    def __init__(self, name: str, *, callbacks: Mapping[str, CallbackType]) -> None:
        self.name = name
        self.callbacks = callbacks


class ComponentInAConstructor(Session):
    recorder: AsPresenter[Dependency]
    taker: AsPresenter[TakingAComponent]


class SharedValueInAConstructor(Session):
    taker: AsPresenter[TakingASharedValue]
    display: AsView[Displaying]


class CatalogueInAConstructor(Session):
    taker: AsPresenter[TakingTheCatalogue]


Counted = NewType("Counted", int)


class CountingCalls:
    """A presenter counting how often the session reads what it shares."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.calls = 0

    @provides
    def counted(self) -> Counted:
        self.calls += 1
        return Counted(self.calls)


class Counting:
    """A presenter holding the shared count it was set up with."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.counted: Counted | None = None

    def setup(self, counted: Counted) -> None:
        self.counted = counted


class CountingApp(Session):
    owner: AsPresenter[CountingCalls]
    first: AsPresenter[Counting]
    second: AsPresenter[Counting]


class Unannotated:
    def __init__(self, name: str, *, thing) -> None:  # type: ignore[no-untyped-def]
        self.name = name


class BadApp(Session):
    broken: AsPresenter[Unannotated]


class VariadicDevice(Device):
    """A device whose constructor would also fail the name check."""

    def __init__(self, *args: object) -> None:
        super().__init__()


class Stray:
    """A view asking for a placement Toy does not attach."""

    placement: Placement = Elsewhere()

    def __init__(self, name: str) -> None:
        self.name = name


class PydanticCtrl(pydantic.BaseModel):
    """Presenter whose fields are keyword-only, as every pydantic model's are."""

    name: str
    devices: DeviceMapping
    gain: float = 2.0

    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)


class PydanticApp(Session):
    motor: AsDevice[MockStage]
    ctrl: Annotated[AsPresenter[PydanticCtrl], Declare(gain=7.5)]


class VariadicName:
    def __init__(self, *name: str) -> None: ...


class KeywordName:
    def __init__(self, *, name: str) -> None:
        self.name = name


class PositionalName:
    def __init__(self, name: str, /) -> None:
        self.name = name


class Tuned(pydantic.BaseModel):
    gain: float = 1.0


class TunedCtrl(Tuned):
    """Presenter whose inherited field comes before `name`."""

    name: str


class PositionalNameApp(Session):
    ctrl: AsPresenter[PositionalName]


class TunedApp(Session):
    ctrl: Annotated[AsPresenter[TunedCtrl], Declare(gain=3.0)]


@dataclass
class DataclassCtrl:
    """Presenter whose annotations live on a generated `__init__`."""

    name: str
    devices: DeviceMapping
    gain: float = 2.0


@dataclass(kw_only=True)
class KwOnlyCtrl:
    """The stdlib route to a keyword-only constructor."""

    name: str
    devices: DeviceMapping
    gain: float = 2.0


@dataclass(frozen=True, slots=True)
class FrozenCtrl:
    """Frozen and slotted, which change what the class carries at runtime."""

    name: str
    devices: DeviceMapping
    gain: float = 2.0


class DataclassApp(Session):
    motor: AsDevice[MockStage]
    ctrl: Annotated[AsPresenter[DataclassCtrl], Declare(gain=7.5)]


class KwOnlyApp(Session):
    motor: AsDevice[MockStage]
    ctrl: Annotated[AsPresenter[KwOnlyCtrl], Declare(gain=7.5)]


class FrozenApp(Session):
    motor: AsDevice[MockStage]
    ctrl: Annotated[AsPresenter[FrozenCtrl], Declare(gain=7.5)]


class SlottedSignal:
    """Presenter with slots and a signal, and no slot for a weak reference."""

    __slots__ = ("name",)

    sig_done = Signal(str)

    def __init__(self, name: str) -> None:
        self.name = name


class WeaklySlottedSignal:
    __slots__ = ("__weakref__", "name")

    sig_done = Signal(str)

    def __init__(self, name: str) -> None:
        self.name = name


@dataclass(slots=True, weakref_slot=True)
class WeakDataclassSignal:
    name: str
    sig_done: ClassVar[Signal] = Signal(str)


class SignalModel(pydantic.BaseModel):
    name: str
    sig_done: ClassVar[Signal] = Signal(str)


@dataclass(frozen=True)
class FrozenWithSetup:
    name: str

    def setup(self, config: SessionConfig) -> None: ...


class FrozenModelWithSetup(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(frozen=True)

    name: str

    def setup(self, config: SessionConfig) -> None: ...


class SlottedSignalApp(Session):
    ctrl: AsPresenter[SlottedSignal]


class WeaklySlottedSignalApp(Session):
    ctrl: AsPresenter[WeaklySlottedSignal]


class WeakDataclassSignalApp(Session):
    ctrl: AsPresenter[WeakDataclassSignal]


class SignalModelApp(Session):
    ctrl: AsPresenter[SignalModel]


class FrozenWithSetupApp(Session):
    ctrl: AsPresenter[FrozenWithSetup]


class FrozenModelWithSetupApp(Session):
    ctrl: AsPresenter[FrozenModelWithSetup]


class Shared(Session):
    """A base holding what every session of one instrument shares."""

    config: ClassVar[Mapping[str, Any]] = {
        "schema_version": 1.0,
        "session": "shared",
        "devices": {"motor": {"axis": "Z"}},
        "presenters": {"ctrl": {"gain": 1.0}},
    }

    motor: AsDevice[MockStage]
    ctrl: AsPresenter[Ctrl]


class Layered(Shared):
    """A session laying its own configuration over the base's."""

    config: ClassVar[Mapping[str, Any]] = {
        "session": "layered",
        "presenters": {"ctrl": {"gain": 9.0}},
    }


class Sideways(Session):
    """A second base, so that Shared can be reached by two paths at once."""

    config: ClassVar[Mapping[str, Any]] = {"devices": {"motor": {"axis": "Y"}}}


class Diamond(Layered, Sideways):
    """Inherits from both, and must resolve the two the way Python does."""


class Ping:
    """Presenter taking `Pong`, which takes this one."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.other: Pong | None = None

    def setup(self, other: Pong) -> None:
        self.other = other


class Pong:
    """The other half of what used to be a cycle."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.other: Ping | None = None

    def setup(self, other: Ping) -> None:
        self.other = other


class CircularApp(Session):
    ping: AsPresenter[Ping]
    pong: AsPresenter[Pong]


Calibration = NewType("Calibration", "float")


Offset = NewType("Offset", "float")


Scale = NewType("Scale", "float")


@dataclass
class DataclassServices:
    """Shared service whose fields are its constructor."""

    config: SessionConfig

    @provides
    def calibration(self) -> Calibration:
        return Calibration(len(self.config.session) / 10)


@dataclass(frozen=True, slots=True)
class FrozenServices:
    """Frozen and slotted, which change what the class carries at runtime."""

    config: SessionConfig

    @provides
    def offset(self) -> Offset:
        return Offset(1.5)


class ModelServices(pydantic.BaseModel):
    """Shared service whose fields are keyword-only and validated."""

    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)

    config: SessionConfig

    @provides
    def scale(self) -> Scale:
        return Scale(2.5)


@dataclass
class NamedServices:
    """Shared service with a field the framework binds on a component."""

    name: str

    @provides
    def scale(self) -> Scale:
        return Scale(0.0)


class Served:
    """Presenter taking one value from each shared service."""

    def __init__(
        self, name: str, *, calibration: Calibration, offset: Offset, scale: Scale
    ) -> None:
        self.name = name
        self.values = (calibration, offset, scale)


class ServicesApp(Session):
    providers: ClassVar[list[type]] = [
        DataclassServices,
        FrozenServices,
        ModelServices,
    ]

    served: AsPresenter[Served]


class NamedServicesApp(Session):
    providers: ClassVar[list[type]] = [NamedServices]

    served: AsPresenter[Served]


class ScaleOwner:
    """Presenter sharing the type a shared service already shares."""

    def __init__(self, name: str) -> None:
        self.name = name

    @provides
    def scale(self) -> Scale:
        return Scale(3.5)


class ProviderAndComponentApp(Session):
    providers: ClassVar[list[type]] = [ModelServices]

    owner: AsPresenter[ScaleOwner]


class DefaultedServices:
    """Shared service whose constructor parameter nothing provides."""

    def __init__(self, factor: float = 2.0) -> None:
        self.factor = factor

    @provides
    def scale(self) -> Scale:
        return Scale(self.factor)


class ScaleReader:
    """Presenter taking the scale a shared service shares."""

    def __init__(self, name: str, *, scale: Scale) -> None:
        self.name = name
        self.scale = scale


class ConfigReader:
    """Presenter keeping the configuration the session was built from."""

    def __init__(self, name: str, *, config: SessionConfig) -> None:
        self.name = name
        self.config = config


class ConfigReaderApp(Session):
    reader: AsPresenter[ConfigReader]


class DefaultedServicesApp(Session):
    providers: ClassVar[list[type]] = [DefaultedServices]

    reader: AsPresenter[ScaleReader]


class BrokenPresenter:
    """Presenter whose construction cannot succeed."""

    def __init__(self, name: str) -> None:
        raise RuntimeError("no hardware")


class BrokenView(Attachable):
    """View whose construction cannot succeed."""

    placement: Placement = Panel("left")

    def __init__(self, name: str) -> None:
        raise RuntimeError("no widget")


class NeedsBroken:
    """Presenter taking one that cannot be constructed."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.other: BrokenPresenter | None = None

    def setup(self, other: BrokenPresenter) -> None:
        self.other = other


class ToleratedApp(Session):
    frontend = Toy

    ok: AsPresenter[Dependency]
    bad: AsPresenter[BrokenPresenter]
    panel: AsView[Attached]
    broken_panel: AsView[BrokenView]


class DependsOnBrokenApp(Session):
    bad: AsPresenter[BrokenPresenter]
    dependent: AsPresenter[NeedsBroken]
    ok: AsPresenter[Dependency]


class Marker:
    """A presenter that records when the build reached its layer."""

    def __init__(self, name: str, steps: list[str]) -> None:
        self.name = name
        steps.append("built the presenter")


class SteppedApp(Session):
    """A session filling the two steps a toolkit owns, and nothing else."""

    ctrl: AsPresenter[Marker]

    def __init__(self, steps: list[str], config: Mapping[str, Any]) -> None:
        super().__init__(config)
        self.steps = steps

    def start_runtime(self) -> None:
        self.steps.append("runtime")

    def present(self) -> None:
        self.steps.append("presentation")


class Unmakeable:
    """A presenter whose constructor raises, so the build skips it."""

    def __init__(self, name: str) -> None:
        raise RuntimeError("this presenter cannot be made")


class Talker:
    """A presenter with one signal."""

    sig_said = Signal(str)

    def __init__(self, name: str) -> None:
        self.name = name


class BrokenTalker(Talker):
    """A talker whose constructor raises, so the build skips it."""

    def __init__(self, name: str) -> None:
        raise RuntimeError("this presenter cannot be made")


class Listener:
    """A presenter recording what it hears."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.heard: list[str] = []

    @slot
    def hear(self, text: str) -> None:
        self.heard.append(text)


class RenamedApp(Session):
    speaker: Annotated[AsPresenter[Talker], Alias("talker")]
    listener: AsPresenter[Listener]

    def wire(self) -> Iterator[Link]:
        yield self.speaker.sig_said, self.listener.hear


class RenamedBrokenApp(Session):
    speaker: Annotated[AsPresenter[BrokenTalker], Alias("talker")]
    listener: AsPresenter[Listener]

    def wire(self) -> Iterator[Link]:
        yield self.speaker.sig_said, self.listener.hear


class MisfiledApp(Session):
    config: ClassVar[Mapping[str, Any]] = {"presenters": {"ctrl": {"gain": 2.0}}}

    stage_ctrl: Annotated[AsPresenter[Ctrl], Alias("ctrl")]


def declaring(target: object, layer: Layer) -> type[Session]:
    """Return a session on `Toy` declaring *target* in *layer* under the name `thing`."""
    hint = Annotated[target, layer]  # type: ignore[valid-type]
    return type(
        "Declaring", (Session,), {"__annotations__": {"thing": hint}, "frontend": Toy}
    )


def asking(hint: object) -> type:
    """Return a presenter class whose constructor asks for a `value` of type *hint*."""

    def __init__(self: Any, name: str, *, value: Any) -> None:
        self.name = name
        self.value = value

    __init__.__annotations__["value"] = hint
    return type("Asking", (), {"__init__": __init__})


def test_build_resolves_every_declaration(app: App) -> None:
    """Build every declared component and device and set each on its attribute."""
    assert app.is_built
    assert isinstance(app.ctrl, Ctrl)
    assert isinstance(app.widget, Widget)
    assert isinstance(app.motor, MockStage)
    assert app.devices == {"motor": app.motor}
    assert run_coro(app.motor.axis.get_value()) == "Z"


def test_config_supplies_kwargs_and_inline_overrides(app: App) -> None:
    """Read kwargs from the config under the attribute name, with Declare first."""
    assert app.ctrl.gain == 2.0
    assert app.widget.label == "inline"
    assert app.name == "test-session"


def test_shared_value_is_bound_to_its_owner(app: App) -> None:
    """Call a @provides method on the built component that declares it."""
    assert app.widget.readings == {"motor": 2.0}


def test_absent_optional_is_none(app: App) -> None:
    """Pass None for an optional parameter whose type nothing provides."""
    assert app.widget.missing is None


def test_default_applies_when_nothing_provides_the_type(app: App) -> None:
    """Keep a parameter's default when the session provides nothing for its type."""
    assert app.tunable.step == 1.5


def test_default_is_overridden_by_what_the_session_provides(app: App) -> None:
    """Fill a defaulted parameter when the session provides its type."""
    assert app.tunable.readings == {"motor": 2.0}


def test_framework_objects_are_injectable(app: App) -> None:
    """Inject the device map and the callback catalogue like any other dependency."""
    assert dict(app.ctrl.devices) == {"motor": app.motor}
    assert app.late.seen == {"registrar": app.registrar}
    assert app.widget.callbacks == {"registrar": app.registrar}


def test_the_container_itself_is_not_injectable() -> None:
    """Refuse a component that asks for the session itself."""
    with pytest.raises(TypeError, match=r"'greedy' asks for 'session' \(Session\)"):
        LocatorApp().build()


def test_shutdown_finalizes_components_in_reverse_declaration_order() -> None:
    """Shut components down in the reverse of their declaration order."""
    teardowns: list[str] = []
    config = {
        "presenters": {
            "first": {"teardowns": teardowns},
            "second": {"teardowns": teardowns},
        }
    }
    OrderedApp(config).build().shutdown()
    assert teardowns == ["first", "second"]


def test_component_shutdown_runs_without_being_asked(app: App) -> None:
    """Call a component's shutdown method without it registering one."""
    registrar = app.registrar
    assert not registrar.closed
    app.shutdown()
    assert registrar.closed


def test_unknown_attribute_raises_attribute_error(app: App) -> None:
    """Raise AttributeError for an attribute the session does not declare."""
    with pytest.raises(AttributeError, match="nonexistent"):
        _ = app.nonexistent  # type: ignore[attr-defined]


def test_rebuild_is_a_no_op(app: App) -> None:
    """Keep the built components when build is called a second time."""
    first = app.ctrl
    app.build()
    assert app.ctrl is first


def test_shutdown_releases_and_allows_gc() -> None:
    """Leave nothing holding a session after its shutdown, so it is collected."""
    container = App().build()
    container.shutdown()
    assert not container.is_built

    collected = weakref.ref(container)
    del container
    gc.collect()
    assert collected() is None


def test_two_components_sharing_one_type_is_refused() -> None:
    """Refuse two components sharing one type, naming both in the error."""
    with pytest.raises(TypeError, match="both share"):
        TwoOwners().build()


def test_two_views_of_one_layer_may_share(build: BuildSession) -> None:
    """Give one view a value another view of the same layer shares."""
    app = build(SameLayerApp)
    assert app.control.viewer is app.display.viewer()


def test_a_view_may_depend_on_a_presenter(build: BuildSession) -> None:
    """Inject a presenter into a view that asks for it."""
    app = build(ViewOnAPresenter)
    assert app.holder.ctrl is app.recorder


@pytest.mark.parametrize(
    ("app", "match"),
    [
        (PresenterOnAViewClass, "'display'"),
        (PresenterOnAViewValue, "'display'"),
    ],
)
def test_a_presenter_depending_on_a_view_is_refused(
    app: type[Session], match: str
) -> None:
    """Refuse a presenter asking for a view class or a value a view shares."""
    with pytest.raises(TypeError, match="knows nothing about a view"):
        app().build()
    with pytest.raises(TypeError, match=match):
        app().build()


@pytest.mark.parametrize(
    ("app", "match"),
    [
        (ComponentInAConstructor, "takes 'recorder' in its 'other' parameter"),
        (SharedValueInAConstructor, "takes 'display' in its 'viewer' parameter"),
        (CatalogueInAConstructor, "takes the callback catalogue"),
    ],
)
def test_a_constructor_taking_what_another_component_owns_is_refused(
    app: type[Session], match: str
) -> None:
    """Refuse a constructor asking for a component, a shared value or the catalogue."""
    with pytest.raises(TypeError, match=match):
        app().build()
    with pytest.raises(TypeError, match="ask for it in 'setup'"):
        app().build()


def test_a_shared_value_is_read_once_at_construction(build: BuildSession) -> None:
    """Call a shared value's provider once and give every consumer that value."""
    app = build(CountingApp)
    assert app.owner.calls == 1
    assert app.first.counted == 1
    assert app.second.counted == 1


def test_unannotated_parameter_is_refused() -> None:
    """Refuse a component whose constructor has an unannotated parameter."""
    with pytest.raises(TypeError, match="has no annotation"):
        BadApp().build()


@pytest.mark.parametrize(
    ("target", "layer"),
    [
        (MockStage, Layer.DEVICE),
        (Ctrl, Layer.PRESENTER),
        (PydanticCtrl, Layer.PRESENTER),
        (KeywordName, Layer.PRESENTER),
        (Attached, Layer.VIEW),
    ],
)
def test_a_class_declared_in_the_layer_it_belongs_to_is_built(
    target: type, layer: Layer, build: BuildSession
) -> None:
    """Build a class declared in its own layer, a keyword-only name and a view the frontend attaches included."""
    app = build(declaring(target, layer))

    assert "thing" in getattr(app, layer.section)


@pytest.mark.parametrize(
    ("target", "layer", "match"),
    [
        (MockStage, Layer.PRESENTER, "is an 'ophyd_async.core.Device'"),
        (MockStage, Layer.VIEW, "is an 'ophyd_async.core.Device'"),
        (VariadicDevice, Layer.PRESENTER, "is an 'ophyd_async.core.Device'"),
        (Ctrl, Layer.DEVICE, "does not subclass 'ophyd_async.core.Device'"),
        (int, Layer.PRESENTER, "does not take 'name'"),
        (VariadicName, Layer.PRESENTER, "does not take 'name'"),
        (Ctrl, Layer.VIEW, "declares no 'placement'"),
        (Widget, Layer.PRESENTER, "declares a 'placement'"),
        (Stray, Layer.VIEW, "does not attach"),
        (Unattachable, Layer.VIEW, "needs a Attachable"),
    ],
)
def test_a_class_declared_in_the_wrong_layer_is_refused_at_declaration(
    target: type,
    layer: Layer,
    match: str,
    build: BuildSession,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Refuse at declaration a class declared in a layer it does not belong to."""
    app = build(declaring(target, layer))

    assert "thing" not in getattr(app, layer.section)
    # the declaration check names the attribute, the check of the built
    # instance names the component
    assert "Declaring.thing" in caplog.text
    assert match in caplog.text


def test_a_declaration_naming_no_class_is_refused() -> None:
    """Refuse a declaration whose type is not a class."""
    with pytest.raises(TypeError, match="is not a class"):
        declaring(int | None, Layer.VIEW)().build()


@pytest.mark.parametrize(
    ("view", "frontend", "placement"),
    [
        (Attached, Toy, Panel("left")),
        (Attached("view"), Toy, Panel("left")),
        (Unattachable, Frontend, Panel("left")),
        (Unattachable, Frontend, Elsewhere()),
    ],
)
def test_a_frontend_accepts_what_it_attaches(
    view: type | object, frontend: type[Frontend], placement: Placement
) -> None:
    """Accept an attachable view class or instance, and any view on a base frontend."""
    frontend.check_placement(view, placement, "somewhere")


@pytest.mark.parametrize(
    ("view", "placement", "match"),
    [
        (Attached, Elsewhere(), "'Elsewhere', which Toy does not attach"),
        (
            Unattachable,
            Panel("left"),
            "needs a Attachable, but Unattachable is not one",
        ),
    ],
)
def test_a_frontend_refuses_what_it_cannot_attach(
    view: type, placement: Placement, match: str
) -> None:
    """Refuse an unattachable placement or view type, naming which one is wrong."""
    with pytest.raises(TypeError, match=match):
        Toy.check_placement(view, placement, "somewhere")


@pytest.mark.parametrize(
    ("app", "protocol"),
    [(NamelessApp, "NamedComponent"), (NamelessViewApp, "AttachableComponent")],
)
def test_a_component_that_drops_its_name_is_skipped(
    app: type[Session],
    protocol: str,
    build: BuildSession,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Skip a component that drops its name, logging only the reason."""
    built = build(app)

    assert not built.presenters
    assert not built.views
    assert f"does not satisfy {protocol!r}: 'name'" in caplog.text
    assert "After injecting" not in caplog.text
    assert "Traceback" not in capsys.readouterr().err


def test_a_view_answering_from_an_instance_is_checked_after_it_is_built(
    build: BuildSession, caplog: pytest.LogCaptureFixture
) -> None:
    """Skip a view whose placement, read from the built instance, is not attachable."""
    app = build(DeferredApp)

    assert "stray" not in app.views
    assert "view 'stray' asks to be attached" in caplog.text


def test_a_component_shadowing_a_container_attribute_is_refused() -> None:
    """Refuse a component named after an existing session attribute."""

    class Shadowed(Session):
        # mypy sees the clash too; the container has to as well
        devices: AsPresenter[Ctrl]  # type: ignore[assignment]

    with pytest.raises(TypeError, match="already an attribute of the session"):
        Shadowed().build()


def test_an_annotation_without_a_layer_is_an_ordinary_attribute(
    caplog: pytest.LogCaptureFixture, build: BuildSession
) -> None:
    """Leave a plain annotation without a layer undeclared and unreported."""

    class Plain(Session):
        threshold: int
        ctrl: AsPresenter[Ctrl]

    app = build(Plain)
    assert set(app.declarations) == {"ctrl"}
    assert "declares no layer" not in caplog.text


def test_a_component_nothing_reaches_is_reported(
    caplog: pytest.LogCaptureFixture, build: BuildSession
) -> None:
    """Log a component that shares nothing, asks for nothing and is wired to nothing."""

    class Inert(Session):
        recorder: AsPresenter[Dependency]

    build(Inert)
    assert (
        "'recorder' shares nothing, asks for nothing and is wired to nothing"
        in caplog.text
    )


def test_a_component_another_is_built_from_is_not_reported(
    caplog: pytest.LogCaptureFixture, build: BuildSession
) -> None:
    """Do not report a component that another component is built from."""

    class WithAnIdlePeer(Session):
        second: Annotated[AsPresenter[Dependent], Alias("second")]
        first: Annotated[AsPresenter[Dependency], Alias("first")]
        idle: AsPresenter[Idle]

    build(WithAnIdlePeer)
    assert "'idle' shares nothing" in caplog.text
    assert "'first' shares nothing" not in caplog.text


def test_a_shared_value_nothing_asks_for_is_reported(
    caplog: pytest.LogCaptureFixture, build: BuildSession
) -> None:
    """Log a shared value that no component asks for."""
    build(App)
    assert (
        "ctrl.descriptions shares 'Descriptions', which no component asks for"
        in caplog.text
    )


def test_a_session_is_named_after_its_class_when_it_says_nothing(
    build: BuildSession,
) -> None:
    """Name a session after its class when its configuration gives no name."""

    class Instrument(Session):
        """A session naming itself nothing."""

    app = build(Instrument)
    assert app.name == "Instrument"


def test_a_forgotten_layer_is_reported(
    caplog: pytest.LogCaptureFixture, build: BuildSession
) -> None:
    """Report an attribute annotated with a component class but no layer."""

    class Forgot(Session):
        ctrl: Ctrl

    app = build(Forgot)
    assert dict(app.declarations) == {}
    assert "Forgot.ctrl annotates Ctrl but declares no layer" in caplog.text


@pytest.mark.parametrize(
    ("hint", "optional"),
    [
        (int | None, True),
        (Readings | None, True),
        (int, False),
        (int | str, False),
        (int | str | None, False),
    ],
)
def test_only_an_optional_parameter_may_go_unanswered(
    hint: object, optional: bool, build: BuildSession
) -> None:
    """Pass `None` for an `X | None` nothing provides, and refuse any other such hint."""
    session = declaring(asking(hint), Layer.PRESENTER)

    if optional:
        presenter = cast("Any", build(session).presenters["thing"])
        assert presenter.value is None
    else:
        with pytest.raises(TypeError, match="which nothing in the session provides"):
            session().build()


def test_a_keyword_only_component_is_built() -> None:
    """Build a pydantic component that takes its name as a keyword."""
    app = PydanticApp().build()
    assert app.ctrl.name == "ctrl"
    assert app.ctrl.gain == 7.5
    assert dict(app.ctrl.devices) == {"motor": app.motor}


def test_a_name_only_a_position_can_fill_is_skipped(
    build: BuildSession, caplog: pytest.LogCaptureFixture
) -> None:
    """Skip a component that takes 'name' only positionally."""
    app = build(PositionalNameApp)

    assert "ctrl" not in app.presenters
    assert "takes 'name' only positionally" in caplog.text


def test_the_name_may_follow_inherited_fields() -> None:
    """Build a model whose name field comes after inherited fields."""
    app = TunedApp().build()
    assert app.ctrl.name == "ctrl"
    assert app.ctrl.gain == 3.0


@pytest.mark.parametrize(
    ("app", "built"),
    [
        (SlottedSignalApp, False),
        (WeaklySlottedSignalApp, True),
        (WeakDataclassSignalApp, True),
        (SignalModelApp, True),
    ],
    ids=["slots", "slots-with-weakref", "dataclass-weakref-slot", "pydantic"],
)
def test_a_component_owning_a_signal_needs_a_weak_reference(
    app: type[Session],
    built: bool,
    build: BuildSession,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Skip a slotted component owning a signal unless it allows weak references."""
    session = build(app)

    assert ("ctrl" in session.presenters) is built
    assert ("without '__weakref__'" in caplog.text) is not built


@pytest.mark.parametrize(
    "frozen",
    [FrozenWithSetupApp, FrozenModelWithSetupApp],
    ids=["dataclass", "pydantic"],
)
def test_a_frozen_component_with_setup_is_built_and_warned_about(
    frozen: type[Session], build: BuildSession, caplog: pytest.LogCaptureFixture
) -> None:
    """Build a frozen component that has setup, and log a warning about it."""
    app = build(frozen)

    assert "ctrl" in app.presenters
    assert "is frozen, so its 'setup' can only assign" in caplog.text


@pytest.mark.parametrize("app", [DataclassApp, KwOnlyApp, FrozenApp])
def test_a_dataclass_is_an_ordinary_component(
    app: type[DataclassApp | KwOnlyApp | FrozenApp],
) -> None:
    """Build plain, keyword-only and frozen dataclass components."""
    built = app().build()
    assert built.ctrl.name == "ctrl"
    assert built.ctrl.gain == 7.5
    assert dict(built.ctrl.devices) == {"motor": built.motor}


def test_a_subclass_layers_over_its_base() -> None:
    """Merge a subclass's configuration over its base class's configuration."""
    app = Layered().build()
    assert app.name == "layered"
    assert app.ctrl.gain == 9.0
    assert run_coro(app.motor.axis.get_value()) == "Z"


def test_layering_follows_the_mro() -> None:
    """Merge configuration from base classes in method resolution order."""
    app = Diamond().build()
    assert run_coro(app.motor.axis.get_value()) == "Z"
    assert app.ctrl.gain == 9.0


def test_the_constructor_layers_over_the_class() -> None:
    """Merge a constructor mapping over the class configuration key by key."""
    app = Layered({"presenters": {"ctrl": {"gain": 4.0}}}).build()
    assert app.ctrl.gain == 4.0
    assert app.name == "layered"
    assert run_coro(app.motor.axis.get_value()) == "Z"


def test_a_file_and_a_mapping_are_both_sources(tmp_path: Path) -> None:
    """Read a string source as a file path and merge it with a mapping."""
    shared = tmp_path / "shared.yaml"
    shared.write_text("session: from-file\npresenters:\n  ctrl:\n    gain: 3.0\n")

    class Mixed(Session):
        config: ClassVar[list[Any]] = [str(shared), {"session": "from-mapping"}]

        motor: AsDevice[MockStage]
        ctrl: AsPresenter[Ctrl]

    app = Mixed().build()
    assert app.name == "from-mapping"
    assert app.ctrl.gain == 3.0


def test_the_sources_read_are_logged_one_per_line(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Log each configuration source on a line of its own, in the order read."""
    shared = tmp_path / "shared.yaml"
    shared.write_text("session: from-file\n")

    class Mixed(Session):
        config: ClassVar[list[Any]] = [str(shared), {"session": "from-mapping"}]

        motor: AsDevice[MockStage]

    caplog.set_level(logging.DEBUG, logger="redsun")
    Mixed().build().shutdown()

    messages = [record.getMessage() for record in caplog.records]
    first = messages.index("Reading configuration from 2 sources, in order:")
    assert messages[first + 1 : first + 3] == [
        f"  1. {shared}",
        "  2. an inline mapping",
    ]


def test_sources_must_agree_on_what_the_session_is() -> None:
    """Refuse configuration sources that name different frontends."""

    class Contradiction(Session):
        config: ClassVar[list[Any]] = [{"frontend": "qt"}, {"frontend": "web"}]

    with pytest.raises(ValueError, match="frontend"):
        Contradiction().build()


def test_a_later_source_may_rename_the_session() -> None:
    """Let a later configuration source change the session name."""

    class Renamed(Session):
        config: ClassVar[list[Any]] = [{"session": "first"}, {"session": "second"}]

    app = Renamed().build()
    assert app.name == "second"


def test_two_components_taking_each_others_values_both_build(
    build: BuildSession,
) -> None:
    """Build two components that each receive the other."""
    app = build(CircularApp)
    assert app.ping.other is app.pong
    assert app.pong.other is app.ping


def test_a_session_knows_what_it_is_called() -> None:
    """Read the session name from the configuration or the class, before the build."""

    class Instrument(Session):
        """A session naming itself nothing."""

    assert Instrument().name == "Instrument"
    assert Instrument({"session": "morning-run"}).name == "morning-run"


def test_a_shared_service_may_be_any_kind_of_class(
    build: BuildSession,
) -> None:
    """Build dataclass, frozen and pydantic shared services and inject their values."""
    app = build(ServicesApp)
    # The first value is derived from the session, which is how the injected
    # `SessionConfig` shows up in what the component receives.
    assert app.served.values == (len(app.name) / 10, 1.5, 2.5)


@pytest.mark.parametrize("mock", [True, False])
def test_a_component_is_told_whether_the_session_is_mocked(mock: bool) -> None:
    """Tell a component asking for `SessionConfig` whether the session is mocked."""
    app = ConfigReaderApp({"mock": mock}).build()
    assert app.reader.config.mock is mock
    app.shutdown()


def test_a_shared_service_is_given_no_name() -> None:
    """Refuse a shared service whose constructor asks for 'name'."""
    with pytest.raises(TypeError, match="'NamedServices' asks for 'name'"):
        NamedServicesApp().build()


def test_a_shared_service_and_a_component_sharing_one_type_is_refused() -> None:
    """Refuse a shared service and a component that share the same type."""
    with pytest.raises(TypeError, match="'owner' and 'ModelServices' both share"):
        ProviderAndComponentApp().build()


def test_a_component_that_fails_to_build_is_skipped(
    build: BuildSession,
) -> None:
    """Skip a component that fails to build and keep every other one."""
    app = build(ToleratedApp)
    assert app.is_built
    assert set(app.presenters) == {"ok"}
    assert set(app.views) == {"panel"}


def test_a_component_that_failed_is_not_set_on_the_session(
    build: BuildSession,
) -> None:
    """Raise AttributeError when reading a component that failed to build."""
    app = build(ToleratedApp)

    with pytest.raises(AttributeError, match="bad"):
        _ = app.bad


def test_a_failure_is_logged_against_the_component_name(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Log each build failure with the component name and the error."""
    with caplog.at_level(logging.ERROR, logger="redsun"):
        ToleratedApp().build().shutdown()

    assert "Failed to build presenter 'bad': no hardware" in caplog.text
    assert "Failed to build view 'broken_panel': no widget" in caplog.text


def test_a_component_whose_collaborator_failed_is_not_set_up(
    build: BuildSession,
) -> None:
    """Build but do not set up a component whose setup needs a failed component."""
    app = build(DependsOnBrokenApp)
    assert app.is_built
    assert set(app.presenters) == {"ok", "dependent"}
    assert app.dependent.other is None


def test_a_provider_keeps_the_default_of_a_parameter_nothing_provides(
    build: BuildSession,
) -> None:
    """Build a provider with its own default where nothing provides the type."""
    app = build(DefaultedServicesApp)
    assert app.reader.scale == 2.0


def test_asking_for_something_nothing_ever_declared_still_raises(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Raise and log when a component asks for a type the session does not provide."""
    with (
        caplog.at_level(logging.ERROR, logger="redsun"),
        pytest.raises(TypeError, match="which nothing in the session provides"),
    ):
        NamedServicesApp().build()

    assert "Build stopped: " in caplog.text
    assert "which nothing in the session provides" in caplog.text


def test_the_closing_line_names_what_is_missing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Log the closing build line as a warning naming each component not built."""
    with caplog.at_level(logging.INFO, logger="redsun"):
        ToleratedApp().build().shutdown()

    closing = [r for r in caplog.records if r.getMessage().startswith("Session built")]
    assert [r.levelno for r in closing] == [logging.WARNING]
    assert "bad (presenter)" in closing[0].getMessage()
    assert "broken_panel (view)" in closing[0].getMessage()


def test_a_session_fills_the_toolkit_steps_rather_than_wrapping_the_build() -> None:
    """Run the runtime step before the components and the presentation step after."""
    steps: list[str] = []
    app = SteppedApp(steps, {"presenters": {"ctrl": {"steps": steps}}}).build()
    try:
        assert steps == ["runtime", "built the presenter", "presentation"]
    finally:
        app.shutdown()


def test_a_session_missing_a_step_cannot_be_constructed() -> None:
    """Refuse to instantiate a session subclass that leaves a build step abstract."""

    # Inheriting the protocol is what makes a missing step refusable: a session
    # answers an unknown attribute with the component of that name, so `isinstance`
    # and a type checker both accept one missing a step, while the abstract members
    # are read off the class when it is created, which no `__getattr__` reaches.
    class Partial(BuildableSession):
        def present(self) -> None: ...

    with pytest.raises(TypeError, match="abstract"):
        Partial()  # type: ignore[abstract]


def test_a_failed_build_gives_back_what_its_finished_steps_took() -> None:
    """Run the releases registered so far, in reverse, when a build step raises."""
    released: list[str] = []

    class Failing(Session):
        def start_runtime(self) -> None:
            self.on_release(lambda: released.append("runtime"))

        def present(self) -> None:
            self.on_release(lambda: released.append("presentation"))
            raise RuntimeError("no window here")

    with pytest.raises(RuntimeError, match="no window here"):
        Failing().build()
    assert released == ["presentation", "runtime"]


def test_shutdown_gives_things_back_in_the_reverse_of_the_order_taken() -> None:
    """Run releases once, in reverse registration order, on shutdown."""
    released: list[str] = []

    class Ordered(Session):
        def start_runtime(self) -> None:
            self.on_release(lambda: released.append("runtime"))

        def present(self) -> None:
            self.on_release(lambda: released.append("presentation"))

    app = Ordered().build()
    assert released == []
    app.shutdown()
    assert released == ["presentation", "runtime"]

    app.shutdown()
    assert released == ["presentation", "runtime"]


@pytest.mark.parametrize(
    "refused", [False, True], ids=["fails-to-build", "refused-at-declaration"]
)
def test_a_wiring_rule_naming_a_skipped_component_is_warned_about(
    refused: bool, caplog: pytest.LogCaptureFixture, build: BuildSession
) -> None:
    """Warn about and skip a wiring rule that names a component not built."""
    rules = {"broken.sig_done": "recorder.on_done"}

    class Half(Session):
        broken: AsPresenter[Unmakeable]
        recorder: AsPresenter[Dependency]

        config: ClassVar[Mapping[str, Any]] = {"wiring": rules}

    class Refused(Session):
        broken: AsPresenter[PositionalName]
        recorder: AsPresenter[Dependency]

        config: ClassVar[Mapping[str, Any]] = {"wiring": rules}

    app = build(Refused if refused else Half)
    assert app.is_built
    assert set(app.presenters) == {"recorder"}
    assert "Not connecting broken.sig_done -> recorder.on_done" in caplog.text
    assert "Not built: broken (presenter)" in caplog.text


def test_a_path_wire_connects_to_a_component_that_failed_is_skipped(
    caplog: pytest.LogCaptureFixture, build: BuildSession
) -> None:
    """Skip a configured wiring rule whose source component failed to build."""

    class Chatty(Session):
        broken: AsPresenter[BrokenTalker]
        listener: AsPresenter[Listener]

        config: ClassVar[Mapping[str, Any]] = {
            "wiring": {"broken.sig_said": "listener.hear"}
        }

    app = build(Chatty)

    assert app.is_built
    assert "Not connecting broken.sig_said -> listener.hear" in caplog.text


def test_a_strict_session_stops_on_a_component_it_could_not_build() -> None:
    """Raise BuildError in strict mode after releasing what the build took."""
    released: list[str] = []

    class Half(Session):
        broken: AsPresenter[Unmakeable]
        recorder: AsPresenter[Dependency]

        def start_runtime(self) -> None:
            self.on_release(lambda: released.append("runtime"))

    with pytest.raises(BuildError, match="broken: this presenter cannot be made"):
        Half({"strict": True}).build()
    assert released == ["runtime"]


def test_a_link_wire_makes_to_a_component_that_failed_is_skipped(
    caplog: pytest.LogCaptureFixture, build: BuildSession
) -> None:
    """Skip a link from a failed component in `wire` and make the others."""

    class Chatty(Session):
        broken: AsPresenter[BrokenTalker]
        talker: AsPresenter[Talker]
        listener: AsPresenter[Listener]

        def wire(self) -> Iterator[Link]:
            yield self.broken.sig_said, self.listener.hear
            yield self.talker.sig_said, self.listener.hear

    app = build(Chatty)
    app.talker.sig_said.emit("hi")

    assert app.listener.heard == ["hi"]
    assert "Not connecting broken.sig_said: component 'broken' was not built" in (
        caplog.text
    )
    with pytest.raises(AttributeError):
        app.broken  # noqa: B018


@pytest.mark.parametrize(
    ("rules", "error", "message"),
    [
        pytest.param(
            {"absent.sig_done": "recorder.on_done"},
            WiringError,
            "names component 'absent', which was not built",
            id="never-declared",
        ),
        pytest.param(
            {"recorder.sig_done": 3},
            ConfigurationError,
            "wiring.recorder.sig_done.str: Input should be a valid string",
            id="value-not-a-string-or-list",
        ),
        pytest.param(
            ["recorder.sig_done -> recorder.on_done"],
            ConfigurationError,
            "wiring: Input should be a valid dictionary",
            id="not-a-mapping",
        ),
    ],
)
def test_a_wiring_rule_wrong_in_any_other_way_stays_fatal(
    rules: Any, error: type[Exception], message: str
) -> None:
    """Raise for a wiring rule naming an undeclared component or of the wrong shape."""

    class Wrong(Session):
        recorder: AsPresenter[Dependency]

        config: ClassVar[Mapping[str, Any]] = {"wiring": rules}

    with pytest.raises(error, match=message):
        Wrong().build()


def test_a_signal_wired_to_a_list_of_slots_in_the_config_reaches_both(
    build: BuildSession,
) -> None:
    """Connect a signal to every slot in a configured list."""

    class Chorus(Session):
        talker: AsPresenter[Talker]
        first: AsPresenter[Listener]
        second: AsPresenter[Listener]

        config: ClassVar[Mapping[str, Any]] = {
            "wiring": {"talker.sig_said": ["first.hear", "second.hear"]}
        }

    app = build(Chorus)
    app.talker.sig_said.emit("hi")

    assert app.first.heard == ["hi"]
    assert app.second.heard == ["hi"]


def test_a_wire_that_yields_nothing_is_fatal() -> None:
    """Raise WiringError when `wire` returns None."""

    class Empty(Session):
        recorder: AsPresenter[Dependency]

        def wire(self) -> None:  # type: ignore[override]
            return None

    with pytest.raises(WiringError, match="wire returned nothing"):
        Empty().build()


def test_a_link_whose_first_item_is_not_a_signal_is_fatal() -> None:
    """Raise WiringError for a link whose first item is not a signal."""

    class Miswired(Session):
        recorder: AsPresenter[Dependency]

        def wire(self) -> Iterator[Link]:
            yield cast("Link", ("not-a-signal", lambda: None))

    with pytest.raises(WiringError, match="is not a signal"):
        Miswired().build()


def test_a_later_layers_wiring_keeps_the_earlier_layers_links(
    build: BuildSession,
) -> None:
    """Merge wiring rules from a later configuration source with earlier ones."""

    class Chatting(Session):
        talker: AsPresenter[Talker]
        chatter: AsPresenter[Talker]
        listener: AsPresenter[Listener]

    first = {"wiring": {"talker.sig_said": "listener.hear"}}
    second = {"wiring": {"chatter.sig_said": "listener.hear"}}

    app = build(Chatting, [first, second])
    app.talker.sig_said.emit("one")
    app.chatter.sig_said.emit("two")

    assert app.listener.heard == ["one", "two"]


def test_a_session_can_be_referred_to_weakly() -> None:
    """Allow a weak reference to a session."""
    # `__slots__` without `__weakref__` refuses a weak reference outright with a
    # `TypeError` from the class, so how long the instance is kept does not matter.
    weakref.ref(Session())


def test_a_renamed_component_is_reached_by_its_attribute() -> None:
    """Reach an aliased component by its attribute and register it under the alias."""
    app = RenamedApp().build()

    app.speaker.sig_said.emit("one")

    assert app.listener.heard == ["one"]
    assert app.speaker.name == "talker"
    assert app.presenters["talker"] is app.speaker
    app.shutdown()


def test_a_renamed_component_that_failed_does_not_break_the_wiring() -> None:
    """Build the rest of the session when an aliased component fails to build."""
    app = RenamedBrokenApp().build()

    assert set(app.presenters) == {"listener"}
    assert app.listener.heard == []
    app.shutdown()


def test_an_entry_read_under_another_key_is_no_component_of_its_own(app: App) -> None:
    """Declare no extra component for an entry `FromConfig` reads under another key."""
    assert "stage" not in app.declarations
    assert set(app.devices) == {"motor"}


def test_an_entry_under_the_name_of_a_renamed_component_is_reported(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Log a config entry filed under a component's alias instead of its attribute."""
    with caplog.at_level(logging.ERROR, logger="redsun"):
        app = MisfiledApp().build()

    assert app.stage_ctrl.gain == 1.0
    assert "presenters.ctrl" in caplog.text
    assert "'stage_ctrl'" in caplog.text
    app.shutdown()


def test_a_session_built_again_starts_from_nothing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Build a session a second time from nothing, keeping no component or failure of the first."""

    class Twice(Session):
        stage: AsDevice[WorksOnce]
        flaky: AsPresenter[FailsOnce]

    config: dict[str, Any] = {
        "devices": {"stage": {"attempts": []}},
        "presenters": {"flaky": {"attempts": []}},
    }
    app = Twice(config)
    app.build()
    app.shutdown()
    caplog.clear()
    app.build()

    try:
        assert "stage" not in app.devices
        assert set(app.presenters) == {"flaky"}
        assert "Not built: flaky" not in caplog.text
    finally:
        app.shutdown()
