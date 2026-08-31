"""Asking the session a question instead of asking for a value."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Annotated, Any, Protocol, get_type_hints, runtime_checkable

import pydantic
import pytest
from ophyd_async.core import Device

from redsun.experimental import (
    Alias,
    AppContainer,
    AsDevice,
    AsPresenter,
    AsView,
    DevicesOf,
    Placement,
    Requires,
    RequiresMaybe,
    RequiresOne,
)
from redsun.experimental.containers._declarations import Declaration, Layer
from redsun.experimental.containers._factories import requirements
from redsun.experimental.virtual._requires import (
    Devices,
    Every,
    Maybe,
    One,
    Question,
    key_for,
    question_of,
)


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


class Session:
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


class App(AppContainer):
    session: AsPresenter[Session]
    motor: AsPresenter[Motor]
    detector: AsPresenter[Detector]
    readout: AsPresenter[Readout]


class PeerApp(AppContainer):
    left: Annotated[AsView[ImageView], Alias("left")]
    middle: Annotated[AsView[ImageView], Alias("middle")]
    right: Annotated[AsView[ImageView], Alias("right")]


class AccidentalApp(AppContainer):
    bookkeeper: AsPresenter[Bookkeeper]
    motor: AsPresenter[Motor]


class LooseApp(AppContainer):
    session: AsPresenter[Session]
    loose: AsPresenter[Loose]


class EagerApp(AppContainer):
    eager: AsPresenter[Eager]
    motor: AsPresenter[Motor]


class UnsatisfiableApp(AppContainer):
    broken: AsPresenter[Unsatisfiable]


class MisshapenApp(AppContainer):
    broken: AsPresenter[Misshapen]


class OneApp(AppContainer):
    roi: AsPresenter[RoiWidget]
    camera: AsPresenter[Camera]


class NoneApp(AppContainer):
    roi: AsPresenter[RoiWidget]


class TwoApp(AppContainer):
    roi: AsPresenter[RoiWidget]
    camera: Annotated[AsPresenter[Camera], Alias("camera")]
    spare: Annotated[AsPresenter[Camera], Alias("spare")]


class SelfApp(AppContainer):
    only: AsPresenter[ImageViewAsking]


class MaybeApp(AppContainer):
    widget: AsPresenter[MaybeWidget]
    camera: AsPresenter[Camera]


class MaybeEmptyApp(AppContainer):
    widget: AsPresenter[MaybeWidget]


class MaybeTwoApp(AppContainer):
    widget: AsPresenter[MaybeWidget]
    camera: Annotated[AsPresenter[Camera], Alias("camera")]
    spare: Annotated[AsPresenter[Camera], Alias("spare")]


class RenamedApp(AppContainer):
    roi: AsPresenter[RoiWidget]
    camera: AsPresenter[Renamed]


class TolerantApp(AppContainer):
    roi: AsPresenter[RoiWidget]
    camera: AsPresenter[Tolerant]


class CountApp(AppContainer):
    needs: AsPresenter[NeedsCount]
    counter: AsPresenter[Counter]


class ForgetfulApp(AppContainer):
    needs: AsPresenter[NeedsCount]
    counter: AsPresenter[Forgetful]


class DataOnlyApp(AppContainer):
    broken: AsPresenter[AsksDataOnly]


class DeviceApp(AppContainer):
    stage: Annotated[AsDevice[Stage], Alias("stage")]
    spare: Annotated[AsDevice[Stage], Alias("spare")]
    shutter: AsDevice[Shutter]
    motors: AsPresenter[MotorPresenter]


class NoDeviceApp(AppContainer):
    motors: AsPresenter[MotorPresenter]


class BothCensusApp(AppContainer):
    stage: AsDevice[Stage]
    both: AsPresenter[AsksBoth]
    motor: AsPresenter[Motor]


class MisshapenDevicesApp(AppContainer):
    broken: AsPresenter[MisshapenDevices]


@pytest.fixture
def app() -> Any:
    container = App().build()
    yield container
    container.shutdown()


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


def test_peers_see_the_whole_set_including_themselves() -> None:
    """The answer describes the session, not the component that asked."""
    app = PeerApp().build()
    try:
        assert sorted(app.left.peers) == ["left", "middle", "right"]
        assert sorted(app.right.peers) == ["left", "middle", "right"]
    finally:
        app.shutdown()


def test_a_peer_leaves_itself_out_where_it_matters() -> None:
    """Only the component knows whether excluding itself is meaningful."""
    app = PeerApp().build()
    try:
        assert app.left.link_targets() == ["middle", "right"]
        assert app.right.link_targets() == ["left", "middle"]
    finally:
        app.shutdown()


def test_peers_act_on_each_other() -> None:
    app = PeerApp().build()
    try:
        app.left.linked_to = "right"
        app.left.zoom_to(4.0)
        assert app.right.zoom == 4.0
        assert app.middle.zoom == 1.0
    finally:
        app.shutdown()


def test_a_component_that_did_not_mean_to_offer_is_still_counted() -> None:
    """Satisfying a protocol by accident puts a component in the answer."""
    app = AccidentalApp().build()
    try:
        app.bookkeeper.reset_all()
        assert app.motor.resets == 1
        assert app.bookkeeper.resets == 1, "it reset itself, which it did not intend"
    finally:
        app.shutdown()


def test_a_mismatched_signature_is_not_a_match() -> None:
    """Membership compares signatures, so a call the protocol permits works."""
    app = LooseApp().build()
    try:
        assert "loose" not in app.session.resettable
        app.session.reset_all()
    finally:
        app.shutdown()


def test_a_near_miss_explains_itself() -> None:
    """A component carrying some of the protocol reports why it was left out."""
    app = LooseApp().build()
    try:
        rejected = app.virtual_container.satisfying(Resettable).rejected
        assert set(rejected) == {"loose"}
        assert "cannot be called as reset()" in rejected["loose"][0]
    finally:
        app.shutdown()


def test_a_component_missing_every_member_is_not_a_near_miss() -> None:
    """Only components that nearly match are worth reporting."""
    app = App().build()
    try:
        assert app.virtual_container.satisfying(Resettable).rejected == {}
    finally:
        app.shutdown()


def test_reading_the_answer_early_is_refused() -> None:
    """During the build the answer would be missing whatever comes next."""
    with pytest.raises(LookupError, match="not known until every component exists"):
        EagerApp().build()


def test_protocol_must_be_runtime_checkable() -> None:
    with pytest.raises(TypeError, match="runtime_checkable"):
        UnsatisfiableApp().build()


def test_marker_on_the_wrong_shape_is_refused() -> None:
    with pytest.raises(TypeError, match="not a 'Mapping\\[str, P\\]'"):
        MisshapenApp().build()


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
    from redsun.experimental.containers._declarations import Declaration, Layer

    declarations = [
        Declaration(Session, "a", Layer.PRESENTER, {}),
        Declaration(Session, "b", Layer.PRESENTER, {}),
    ]
    assert requirements(declarations) == {Question(Resettable, Every()): ["a", "b"]}


def test_one_arrives_built() -> None:
    """Unlike a census, a single answer is an ordinary dependency."""
    app = OneApp().build()
    try:
        assert app.roi.camera is app.camera
        app.roi.zoom_to(3.0)
        assert app.camera.zoom == 3.0
    finally:
        app.shutdown()


def test_one_refuses_an_empty_session() -> None:
    with pytest.raises(TypeError, match="the session holds none"):
        NoneApp().build()


def test_one_refuses_an_ambiguous_session() -> None:
    with pytest.raises(TypeError, match="but 2 do: 'camera' and 'spare'"):
        TwoApp().build()


def test_one_refuses_to_answer_with_the_asker() -> None:
    """A component cannot depend on itself."""
    with pytest.raises(TypeError, match="is the only one that does"):
        SelfApp().build()


def test_maybe_is_answered_when_present() -> None:
    app = MaybeApp().build()
    try:
        assert app.widget.camera is app.camera
    finally:
        app.shutdown()


def test_maybe_is_none_when_absent() -> None:
    app = MaybeEmptyApp().build()
    try:
        assert app.widget.camera is None
    finally:
        app.shutdown()


def test_maybe_still_refuses_two_answers() -> None:
    """The parameter has room for one, so several is a mistake either way."""
    with pytest.raises(TypeError, match="at most one component"):
        MaybeTwoApp().build()


def test_a_renamed_parameter_does_not_answer() -> None:
    """The keyword call the protocol permits would fail, so it is not a match."""
    with pytest.raises(TypeError, match="the session holds none"):
        RenamedApp().build()


def test_a_near_miss_is_named_when_nothing_answers() -> None:
    with pytest.raises(TypeError, match=r"'camera': apply_camera\(factor"):
        RenamedApp().build()


def test_an_extra_defaulted_parameter_still_answers() -> None:
    """Widening an implementation does not break the protocol's calls."""
    app = TolerantApp().build()
    try:
        assert app.roi.camera is app.camera
        app.roi.zoom_to(2.0)
        assert app.camera.zoom == 2.0
    finally:
        app.shutdown()


def test_a_data_member_assigned_in_init_still_answers() -> None:
    """The choice ignores what only an instance can show, then confirms it."""
    app = CountApp().build()
    try:
        assert app.needs.counter is app.counter
    finally:
        app.shutdown()


def test_a_data_member_never_assigned_is_caught_after_the_build() -> None:
    with pytest.raises(TypeError, match=r"but does not: 'count' is missing"):
        ForgetfulApp().build()


def test_a_protocol_with_no_method_cannot_be_asked_for_one() -> None:
    with pytest.raises(TypeError, match="declares no method"):
        DataOnlyApp().build()


def test_the_device_census_holds_every_matching_device() -> None:
    app = DeviceApp().build()
    try:
        assert dict(app.motors.motors) == {"stage": app.stage, "spare": app.spare}
    finally:
        app.shutdown()


def test_a_device_that_does_not_match_is_absent() -> None:
    app = DeviceApp().build()
    try:
        assert "shutter" not in app.motors.motors
    finally:
        app.shutdown()


def test_the_device_census_is_readable_while_the_component_is_built() -> None:
    """Every device exists before any component, so the answer is not a live view."""
    app = DeviceApp().build()
    try:
        assert app.motors.names == ["spare", "stage"]
    finally:
        app.shutdown()


def test_the_device_census_is_empty_without_devices() -> None:
    app = NoDeviceApp().build()
    try:
        assert dict(app.motors.motors) == {}
    finally:
        app.shutdown()


def test_the_two_censuses_answer_over_different_populations() -> None:
    """A device is never in the component census, and a component never in this one."""
    app = BothCensusApp().build()
    try:
        assert sorted(app.both.motors) == ["stage"]
        assert sorted(app.both.resettable) == ["motor"]
    finally:
        app.shutdown()


def test_devices_of_expands_to_an_annotated_mapping() -> None:
    assert question_of(DevicesOf[Movable]) == Question(Movable, Devices())


def test_a_device_census_and_a_component_census_are_different_questions() -> None:
    """Same protocol, different population, so they cannot share one answer."""
    assert key_for(Question(Movable, Devices())) is not key_for(
        Question(Movable, Every())
    )


def test_the_device_marker_on_the_wrong_shape_names_its_own_spelling() -> None:
    with pytest.raises(TypeError, match=r"Write 'DevicesOf\[P\]'"):
        MisshapenDevicesApp().build()


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


class BackwardsQuestionApp(AppContainer):
    ctrl: AsPresenter[WantsTheCanvas]
    canvas: AsView[Canvas]


def test_a_question_answered_by_a_later_layer_is_refused() -> None:
    """Choosing the one component cannot choose one built after the asker."""
    with pytest.raises(TypeError, match="is built before a view"):
        BackwardsQuestionApp().build()


class PydanticSession(pydantic.BaseModel):
    """Presenter asking a question from a class that synthesizes its signature."""

    name: str
    resettable: Requires[Resettable]

    model_config = pydantic.ConfigDict(arbitrary_types_allowed=True)


def test_a_keyword_only_component_asks_the_same_question() -> None:
    """The marker is read off the signature, which is where pydantic keeps it."""
    declarations = [
        Declaration(Session, "plain", Layer.PRESENTER, {}),
        Declaration(PydanticSession, "pyd", Layer.PRESENTER, {}),
    ]
    assert requirements(declarations) == {
        Question(Resettable, Every()): ["plain", "pyd"]
    }
