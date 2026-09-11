"""Asking the session a question instead of asking for a value."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .conftest import BuildSession

import logging
from collections.abc import (
    Mapping,
)
from dataclasses import dataclass
from typing import Annotated, Any, Protocol, get_type_hints, runtime_checkable

import pydantic
import pytest
from ophyd_async.core import Device

from redsun.experimental import (
    Alias,
    AsDevice,
    AsPresenter,
    AsView,
    DevicesOf,
    Placement,
    Requires,
    RequiresBuilt,
    RequiresMaybe,
    RequiresOne,
    Session,
)
from redsun.experimental.injection import (
    Built,
    Devices,
    Every,
    Maybe,
    One,
    Question,
    key_for,
    question_of,
)
from redsun.experimental.session import Declaration, Layer, requirements


@dataclass(frozen=True)
class Somewhere(Placement):
    """Stand-in placement: the core ships none, and no frontend is named here."""


@runtime_checkable
class Resettable(Protocol):
    """Anything the session can put back to its initial state."""

    def reset(self) -> None: ...


class Unchecked(Protocol):
    """Deliberately not runtime-checkable."""

    def ping(self) -> None: ...


class Motor:
    """Presenter that can be reset."""

    def __init__(self, name: str, /) -> None:
        self.name = name
        self.resets = 0

    def reset(self) -> None:
        self.resets += 1


class Detector:
    """Another one, so the answer has more than one entry."""

    def __init__(self, name: str, /) -> None:
        self.name = name
        self.resets = 0

    def reset(self) -> None:
        self.resets += 1


class Readout:
    """Component that cannot be reset, so it stays out of the answer."""

    def __init__(self, name: str, /) -> None:
        self.name = name


class Resetter:
    """Presenter driving every resettable component in the session."""

    def __init__(self, name: str, /, resettable: Requires[Resettable]) -> None:
        self.name = name
        self.resettable = resettable

    def reset_all(self) -> None:
        for component in self.resettable.values():
            component.reset()


class Eager:
    """Presenter reading the answer while it is still being assembled."""

    def __init__(self, name: str, /, resettable: Requires[Resettable]) -> None:
        self.name = name
        self.copy = dict(resettable)


class Unsatisfiable:
    """Presenter asking about a protocol isinstance cannot check."""

    def __init__(self, name: str, /, pingable: Requires[Unchecked]) -> None:
        self.name = name


class Misshapen:
    """Presenter carrying the marker on the wrong shape."""

    def __init__(
        self, name: str, /, wrong: Annotated[list[Resettable], Every()]
    ) -> None:
        self.name = name


@runtime_checkable
class Linkable(Protocol):
    """A viewer whose camera another viewer can drive."""

    name: str

    def apply_camera(self, zoom: float) -> None: ...


class ImageView:
    """Peer component: it both offers the capability and asks about it."""

    placement: Placement = Somewhere()

    def __init__(self, name: str, /, peers: Requires[Linkable]) -> None:
        self.name = name
        self.peers = peers
        self.zoom = 1.0
        self.linked_to: str | None = None

    def link_targets(self) -> list[str]:
        """Return what this widget's 'link to...' menu offers."""
        return sorted(name for name in self.peers if name != self.name)

    def zoom_to(self, zoom: float) -> None:
        self.zoom = zoom
        for name, peer in self.peers.items():
            if name == self.linked_to:
                peer.apply_camera(zoom)

    def apply_camera(self, zoom: float) -> None:
        self.zoom = zoom


class Bookkeeper:
    """Presenter with a reset of its own, which it never meant to offer."""

    def __init__(self, name: str, /, resettable: Requires[Resettable]) -> None:
        self.name = name
        self.resettable = resettable
        self.resets = 0

    def reset(self) -> None:
        self.resets += 1

    def reset_all(self) -> None:
        for component in self.resettable.values():
            component.reset()


class Loose:
    """Its reset takes an argument the protocol does not permit passing."""

    def __init__(self, name: str, /) -> None:
        self.name = name

    def reset(self, hard: bool) -> None: ...


class Renamed:
    """Its parameter name differs, so a keyword call would fail."""

    def __init__(self, name: str, /) -> None:
        self.name = name

    def apply_camera(self, factor: float) -> None: ...


class Tolerant:
    """An extra defaulted parameter still accepts every permitted call."""

    def __init__(self, name: str, /) -> None:
        self.name = name
        self.zoom = 1.0

    def apply_camera(self, zoom: float, smooth: bool = False) -> None:
        self.zoom = zoom


class RoiWidget:
    """Asks for the one camera in the session and drives it."""

    def __init__(self, name: str, /, camera: RequiresOne[Linkable]) -> None:
        self.name = name
        self.camera = camera

    def zoom_to(self, zoom: float) -> None:
        self.camera.apply_camera(zoom)


class MaybeWidget:
    """Asks for a camera it can do without."""

    def __init__(self, name: str, /, camera: RequiresMaybe[Linkable] = None) -> None:
        self.name = name
        self.camera = camera


class ImageViewAsking:
    """Offers Linkable and asks for the one component offering it."""

    def __init__(self, name: str, /, peer: RequiresOne[Linkable]) -> None:
        self.name = name
        self.peer = peer

    def apply_camera(self, zoom: float) -> None: ...


class Camera:
    """The single component satisfying Linkable."""

    def __init__(self, name: str, /) -> None:
        self.name = name
        self.zoom = 1.0

    def apply_camera(self, zoom: float) -> None:
        self.zoom = zoom


@runtime_checkable
class DataOnly(Protocol):
    """Nothing callable, so no component can be chosen before the build."""

    label: str


@runtime_checkable
class Countable(Protocol):
    """Satisfied only by an attribute assigned in ``__init__``."""

    count: int

    def bump(self) -> None: ...


class Counter:
    """Its ``count`` exists only once constructed."""

    def __init__(self, name: str, /) -> None:
        self.name = name
        self.count = 0

    def bump(self) -> None:
        self.count += 1


class Forgetful:
    """Passes the class-level check but never assigns ``count``."""

    def __init__(self, name: str, /) -> None:
        self.name = name

    def bump(self) -> None: ...


class NeedsCount:
    """Asks for the one countable component."""

    def __init__(self, name: str, /, counter: RequiresOne[Countable]) -> None:
        self.name = name
        self.counter = counter


class AsksDataOnly:
    """Asks a single-answer question about a protocol with no method."""

    def __init__(self, name: str, /, label: RequiresOne[DataOnly]) -> None:
        self.name = name


@runtime_checkable
class Movable(Protocol):
    """A device that can be told where to go."""

    async def move(self, position: float) -> None: ...


class Stage(Device):
    """Device answering the device census."""

    def __init__(self, name: str, /) -> None:
        super().__init__(name=name)
        self.position = 0.0

    async def move(self, position: float) -> None:
        self.position = position


class Shutter(Device):
    """Device that cannot move, so it stays out of the answer."""


class MotorPresenter:
    """Presenter reading the device census while it is built."""

    def __init__(self, name: str, /, motors: DevicesOf[Movable]) -> None:
        self.name = name
        self.motors = motors
        self.names = sorted(motors)


class AsksBoth:
    """Asks both censuses, which are answered over different populations."""

    def __init__(
        self,
        name: str,
        /,
        motors: DevicesOf[Movable],
        resettable: Requires[Resettable],
    ) -> None:
        self.name = name
        self.motors = motors
        self.resettable = resettable


class MisshapenDevices:
    """Presenter carrying the device marker on the wrong shape."""

    def __init__(
        self, name: str, /, wrong: Annotated[list[Movable], Devices()]
    ) -> None:
        self.name = name


class Collector:
    """Presenter reading, while it is built, the resettable components built first."""

    def __init__(self, name: str, /, resettable: RequiresBuilt[Resettable]) -> None:
        self.name = name
        self.resettable = resettable
        self.names = list(resettable)


class SelfCollector:
    """Resettable itself, and asking about the resettable components built first."""

    def __init__(self, name: str, /, resettable: RequiresBuilt[Resettable]) -> None:
        self.name = name
        self.names = list(resettable)

    def reset(self) -> None: ...


class Unplugged:
    """Resettable, and cannot be built."""

    def __init__(self, name: str, /) -> None:
        raise RuntimeError("unplugged")

    def reset(self) -> None: ...


class ResettableView:
    """View that can be reset, so a presenter's census would need it first."""

    placement: Placement = Somewhere()

    def __init__(self, name: str, /) -> None:
        self.name = name

    def reset(self) -> None: ...


class AsksBuiltDataOnly:
    """Asks for the components built first about a protocol with no method."""

    def __init__(self, name: str, /, labels: RequiresBuilt[DataOnly]) -> None:
        self.name = name


class BuiltApp(Session):
    collector: AsPresenter[Collector]
    motor: AsPresenter[Motor]
    readout: AsPresenter[Readout]
    detector: AsPresenter[Detector]


class BuiltSelfApp(Session):
    collector: AsPresenter[SelfCollector]
    motor: AsPresenter[Motor]


class BuiltUnpluggedApp(Session):
    collector: AsPresenter[Collector]
    broken: AsPresenter[Unplugged]
    motor: AsPresenter[Motor]


class BuiltBackwardsApp(Session):
    collector: AsPresenter[Collector]
    panel: AsView[ResettableView]


class BuiltCycleApp(Session):
    first: AsPresenter[SelfCollector]
    second: AsPresenter[SelfCollector]


class BuiltDataOnlyApp(Session):
    asks: AsPresenter[AsksBuiltDataOnly]


class App(Session):
    session: AsPresenter[Resetter]
    motor: AsPresenter[Motor]
    detector: AsPresenter[Detector]
    readout: AsPresenter[Readout]


class PeerApp(Session):
    left: Annotated[AsView[ImageView], Alias("left")]
    middle: Annotated[AsView[ImageView], Alias("middle")]
    right: Annotated[AsView[ImageView], Alias("right")]


class AccidentalApp(Session):
    bookkeeper: AsPresenter[Bookkeeper]
    motor: AsPresenter[Motor]


class LooseApp(Session):
    session: AsPresenter[Resetter]
    loose: AsPresenter[Loose]


class EagerApp(Session):
    eager: AsPresenter[Eager]
    motor: AsPresenter[Motor]


class UnsatisfiableApp(Session):
    broken: AsPresenter[Unsatisfiable]


class MisshapenApp(Session):
    broken: AsPresenter[Misshapen]


class OneApp(Session):
    roi: AsPresenter[RoiWidget]
    camera: AsPresenter[Camera]


class NoneApp(Session):
    roi: AsPresenter[RoiWidget]


class TwoApp(Session):
    roi: AsPresenter[RoiWidget]
    camera: Annotated[AsPresenter[Camera], Alias("camera")]
    spare: Annotated[AsPresenter[Camera], Alias("spare")]


class SelfApp(Session):
    only: AsPresenter[ImageViewAsking]


class MaybeApp(Session):
    widget: AsPresenter[MaybeWidget]
    camera: AsPresenter[Camera]


class MaybeEmptyApp(Session):
    widget: AsPresenter[MaybeWidget]


class MaybeTwoApp(Session):
    widget: AsPresenter[MaybeWidget]
    camera: Annotated[AsPresenter[Camera], Alias("camera")]
    spare: Annotated[AsPresenter[Camera], Alias("spare")]


class RenamedApp(Session):
    roi: AsPresenter[RoiWidget]
    camera: AsPresenter[Renamed]


class TolerantApp(Session):
    roi: AsPresenter[RoiWidget]
    camera: AsPresenter[Tolerant]


class CountApp(Session):
    needs: AsPresenter[NeedsCount]
    counter: AsPresenter[Counter]


class ForgetfulApp(Session):
    needs: AsPresenter[NeedsCount]
    counter: AsPresenter[Forgetful]


class DataOnlyApp(Session):
    broken: AsPresenter[AsksDataOnly]


class DeviceApp(Session):
    stage: Annotated[AsDevice[Stage], Alias("stage")]
    spare: Annotated[AsDevice[Stage], Alias("spare")]
    shutter: AsDevice[Shutter]
    motors: AsPresenter[MotorPresenter]


class NoDeviceApp(Session):
    motors: AsPresenter[MotorPresenter]


class BothCensusApp(Session):
    stage: AsDevice[Stage]
    both: AsPresenter[AsksBoth]
    motor: AsPresenter[Motor]


class MisshapenDevicesApp(Session):
    broken: AsPresenter[MisshapenDevices]


@pytest.fixture
def app() -> Any:
    container = App().build()
    yield container
    container.shutdown()


@runtime_checkable
class Displayable(Protocol):
    """Something the session can show."""

    def show(self) -> None: ...


class Canvas:
    """A view, and the only component that can be shown."""

    placement: Placement = Somewhere()

    def __init__(self, name: str, /) -> None:
        self.name = name

    def show(self) -> None: ...


class WantsTheCanvas:
    """A presenter asking for the one displayable, which is a view."""

    def __init__(self, name: str, /, canvas: RequiresOne[Displayable]) -> None:
        self.name = name
        self.canvas = canvas


class BackwardsQuestionApp(Session):
    ctrl: AsPresenter[WantsTheCanvas]
    canvas: AsView[Canvas]


class PydanticSession(pydantic.BaseModel):
    """Presenter asking a question from a class that synthesizes its signature."""

    name: str
    resettable: Requires[Resettable]

    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)


class BrokenCamera:
    """The one component satisfying `Linkable`, which cannot be built."""

    def __init__(self, name: str, /) -> None:
        raise RuntimeError("no camera")

    def apply_camera(self, zoom: float) -> None: ...


class AsksAboutLinkables:
    """Holds the census of `Linkable`, so it can be read after the build."""

    def __init__(self, name: str, /, peers: Requires[Linkable]) -> None:
        self.name = name
        self.peers = peers


class CensusReaderApp(Session):
    camera: AsPresenter[Camera]
    broken: AsPresenter[BrokenCamera]
    reader: AsPresenter[AsksAboutLinkables]


class BrokenOneApp(Session):
    """Asks for the one `Linkable`, which cannot be built."""

    broken: AsPresenter[BrokenCamera]
    roi: AsPresenter[RoiWidget]


class BrokenMaybeApp(Session):
    """Asks for a `Linkable` it can do without, which cannot be built."""

    broken: AsPresenter[BrokenCamera]
    widget: AsPresenter[MaybeWidget]


def test_the_answer_holds_every_matching_component(app: App) -> None:
    """Declaration order does not matter: the question is answered after the build."""
    assert dict(app.session.resettable) == {
        "motor": app.motor,
        "detector": app.detector,
    }


def test_a_component_that_does_not_match_is_absent(app: App) -> None:
    assert "readout" not in app.session.resettable


def test_the_answer_is_usable_as_a_mapping(app: App) -> None:
    """It is a plain Mapping, so a component needs no framework API to read it."""
    assert isinstance(app.session.resettable, Mapping)
    assert len(app.session.resettable) == 2
    assert sorted(app.session.resettable) == ["detector", "motor"]


def test_driving_every_component_through_the_answer(app: App) -> None:
    app.session.reset_all()
    assert (app.motor.resets, app.detector.resets) == (1, 1)


def test_peers_see_the_whole_set_including_themselves(
    build: BuildSession,
) -> None:
    """The answer describes the session, not the component that asked."""
    app = build(PeerApp)
    assert sorted(app.left.peers) == ["left", "middle", "right"]
    assert sorted(app.right.peers) == ["left", "middle", "right"]


def test_a_peer_leaves_itself_out_where_it_matters(
    build: BuildSession,
) -> None:
    """Only the component knows whether excluding itself is meaningful."""
    app = build(PeerApp)
    assert app.left.link_targets() == ["middle", "right"]
    assert app.right.link_targets() == ["left", "middle"]


def test_peers_act_on_each_other(build: BuildSession) -> None:
    app = build(PeerApp)
    app.left.linked_to = "right"
    app.left.zoom_to(4.0)
    assert app.right.zoom == 4.0
    assert app.middle.zoom == 1.0


def test_a_component_that_did_not_mean_to_offer_is_still_counted(
    build: BuildSession,
) -> None:
    """Satisfying a protocol by accident puts a component in the answer."""
    app = build(AccidentalApp)
    app.bookkeeper.reset_all()
    assert app.motor.resets == 1
    assert app.bookkeeper.resets == 1, "it reset itself, which it did not intend"


def test_a_mismatched_signature_is_not_a_match(
    build: BuildSession,
) -> None:
    """Membership compares signatures, so a call the protocol permits works."""
    app = build(LooseApp)
    assert "loose" not in app.session.resettable
    app.session.reset_all()


def test_a_near_miss_explains_itself(build: BuildSession) -> None:
    """A component carrying some of the protocol reports why it was left out."""
    app = build(LooseApp)
    rejected = app.satisfying(Resettable).rejected
    assert set(rejected) == {"loose"}
    assert "cannot be called as reset()" in rejected["loose"][0]


def test_a_component_missing_every_member_is_not_a_near_miss(
    build: BuildSession,
) -> None:
    """Only components that nearly match are worth reporting."""
    app = build(App)
    assert app.satisfying(Resettable).rejected == {}


@pytest.mark.parametrize(
    ("session", "error", "match"),
    [
        pytest.param(
            EagerApp,
            LookupError,
            "not known until every component exists",
            id="census-read-while-built",
        ),
        pytest.param(
            UnsatisfiableApp,
            TypeError,
            "runtime_checkable",
            id="protocol-not-runtime-checkable",
        ),
        pytest.param(
            MisshapenApp,
            TypeError,
            r"not a 'Mapping\[str, P\]'",
            id="census-on-the-wrong-shape",
        ),
        pytest.param(
            MisshapenDevicesApp,
            TypeError,
            r"Write 'DevicesOf\[P\]'",
            id="device-census-on-the-wrong-shape",
        ),
        pytest.param(
            NoneApp, TypeError, "the session holds none", id="one-answered-by-none"
        ),
        pytest.param(
            TwoApp,
            TypeError,
            "but 2 do: 'camera' and 'spare'",
            id="one-answered-by-two",
        ),
        pytest.param(
            SelfApp,
            TypeError,
            "is the only one that does",
            id="one-answered-by-the-asker",
        ),
        pytest.param(
            MaybeTwoApp,
            TypeError,
            "at most one component",
            id="maybe-answered-by-two",
        ),
        pytest.param(
            RenamedApp,
            TypeError,
            "the session holds none",
            id="renamed-parameter-does-not-answer",
        ),
        pytest.param(
            RenamedApp,
            TypeError,
            r"'camera': apply_camera\(factor",
            id="near-miss-is-named",
        ),
        pytest.param(
            ForgetfulApp,
            TypeError,
            "but does not: 'count' is missing",
            id="data-member-never-assigned",
        ),
        pytest.param(
            DataOnlyApp,
            TypeError,
            "declares no method",
            id="one-about-a-protocol-with-no-method",
        ),
        pytest.param(
            BackwardsQuestionApp,
            TypeError,
            "is built before a view",
            id="one-answered-by-a-later-layer",
        ),
        pytest.param(
            BuiltBackwardsApp,
            TypeError,
            "is built before a view",
            id="built-answered-by-a-later-layer",
        ),
        pytest.param(
            BuiltCycleApp,
            TypeError,
            "built from each other",
            id="built-askers-answering-each-other",
        ),
        pytest.param(
            BuiltDataOnlyApp,
            TypeError,
            "declares no method",
            id="built-about-a-protocol-with-no-method",
        ),
    ],
)
def test_the_session_refuses_to_build(
    session: type[Session], error: type[Exception], match: str
) -> None:
    with pytest.raises(error, match=match):
        session().build()


def test_requires_expands_to_an_annotated_mapping() -> None:
    """The spelling is short, but the type stays an ordinary Mapping."""
    assert question_of(Requires[Resettable]) == Question(Resettable, Every())
    assert question_of(Mapping[str, Resettable]) is None
    assert question_of(int) is None


@pytest.mark.parametrize(
    ("cls", "param", "expected"),
    [
        (ImageView, "peers", Question(Linkable, Every())),
        (RoiWidget, "camera", Question(Linkable, One())),
        (MaybeWidget, "camera", Question(Linkable, Maybe())),
        (Collector, "resettable", Question(Resettable, Built())),
    ],
)
def test_each_spelling_carries_its_cardinality(
    cls: type, param: str, expected: Question
) -> None:
    """Read from the annotation, which is where the container finds it."""
    hint = get_type_hints(cls.__init__, include_extras=True)[param]  # type: ignore[misc]
    assert question_of(hint) == expected


def test_one_key_per_question() -> None:
    """Two components asking the same question share one answer."""
    census = Question(Resettable, Every())
    assert key_for(census) is key_for(Question(Resettable, Every()))
    assert key_for(census) is not key_for(Question(Resettable, One()))
    assert key_for(census) is not key_for(Question(Unchecked, Every()))


def test_requirements_are_collected_once_per_question() -> None:
    declarations = [
        Declaration(Resetter, "a", Layer.PRESENTER, {}),
        Declaration(Resetter, "b", Layer.PRESENTER, {}),
    ]
    assert requirements(declarations) == {Question(Resettable, Every()): ["a", "b"]}


def test_one_arrives_built(build: BuildSession) -> None:
    """Unlike a census, a single answer is an ordinary dependency."""
    app = build(OneApp)
    assert app.roi.camera is app.camera
    app.roi.zoom_to(3.0)
    assert app.camera.zoom == 3.0


def test_maybe_is_answered_when_present(build: BuildSession) -> None:
    app = build(MaybeApp)
    assert app.widget.camera is app.camera


def test_maybe_is_none_when_absent(build: BuildSession) -> None:
    app = build(MaybeEmptyApp)
    assert app.widget.camera is None


def test_an_extra_defaulted_parameter_still_answers(
    build: BuildSession,
) -> None:
    """Widening an implementation does not break the protocol's calls."""
    app = build(TolerantApp)
    assert app.roi.camera is app.camera
    app.roi.zoom_to(2.0)
    assert app.camera.zoom == 2.0


def test_a_data_member_assigned_in_init_still_answers(
    build: BuildSession,
) -> None:
    """The choice ignores what only an instance can show, then confirms it."""
    app = build(CountApp)
    assert app.needs.counter is app.counter


def test_the_device_census_holds_every_matching_device(
    build: BuildSession,
) -> None:
    app = build(DeviceApp)
    assert dict(app.motors.motors) == {"stage": app.stage, "spare": app.spare}


def test_a_device_that_does_not_match_is_absent(
    build: BuildSession,
) -> None:
    app = build(DeviceApp)
    assert "shutter" not in app.motors.motors


def test_the_device_census_is_readable_while_the_component_is_built(
    build: BuildSession,
) -> None:
    """Every device exists before any component, so the answer is not a live view."""
    app = build(DeviceApp)
    assert app.motors.names == ["spare", "stage"]


def test_the_device_census_is_empty_without_devices(
    build: BuildSession,
) -> None:
    app = build(NoDeviceApp)
    assert dict(app.motors.motors) == {}


def test_the_two_censuses_answer_over_different_populations(
    build: BuildSession,
) -> None:
    """A device is never in the component census, and a component never in this one."""
    app = build(BothCensusApp)
    assert sorted(app.both.motors) == ["stage"]
    assert sorted(app.both.resettable) == ["motor"]


def test_devices_of_expands_to_an_annotated_mapping() -> None:
    assert question_of(DevicesOf[Movable]) == Question(Movable, Devices())


def test_a_device_census_and_a_component_census_are_different_questions() -> None:
    """Same protocol, different population, so they cannot share one answer."""
    assert key_for(Question(Movable, Devices())) is not key_for(
        Question(Movable, Every())
    )


def test_the_built_census_is_complete_while_the_component_is_built(
    build: BuildSession,
) -> None:
    """Declared above the components answering it, the asker is built after them."""
    app = build(BuiltApp)
    assert app.collector.names == ["motor", "detector"]
    assert app.collector.resettable == {"motor": app.motor, "detector": app.detector}


def test_the_asker_is_not_in_its_own_built_census(build: BuildSession) -> None:
    app = build(BuiltSelfApp)
    assert app.collector.names == ["motor"]


def test_a_component_that_failed_is_absent_from_the_built_census(
    build: BuildSession,
) -> None:
    app = build(BuiltUnpluggedApp)
    assert app.collector.names == ["motor"]


def test_a_keyword_only_component_asks_the_same_question() -> None:
    """The marker is read off the signature, which is where pydantic keeps it."""
    declarations = [
        Declaration(Resetter, "plain", Layer.PRESENTER, {}),
        Declaration(PydanticSession, "pyd", Layer.PRESENTER, {}),
    ]
    assert requirements(declarations) == {
        Question(Resettable, Every()): ["plain", "pyd"]
    }


def test_the_census_leaves_out_a_component_that_failed(
    build: BuildSession,
) -> None:
    """A component asks what the session holds, not what it declared."""
    app = build(CensusReaderApp)
    assert set(app.reader.peers) == {"camera"}


def test_the_one_answer_failing_skips_whoever_asked(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Exactly one was demanded, so `None` is not an answer the asker can take."""
    with caplog.at_level(logging.ERROR, logger="redsun"):
        app = BrokenOneApp().build()
    try:
        assert app.is_built
        assert set(app.presenters) == set()
        assert "Failed to build presenter 'roi': 'broken' was not built" in caplog.text
    finally:
        app.shutdown()


def test_an_optional_answer_failing_leaves_the_asker_without_one(
    build: BuildSession,
) -> None:
    """At most one was asked for, and the session ended up holding none."""
    app = build(BrokenMaybeApp)
    assert set(app.presenters) == {"widget"}
    assert app.widget.camera is None
