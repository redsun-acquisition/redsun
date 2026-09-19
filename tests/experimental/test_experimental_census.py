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
from typing import Annotated, Any, Protocol, runtime_checkable

import pytest
from ophyd_async.core import (
    AsyncStatus,
    StandardReadable,
    StandardReadableFormat,
    soft_signal_rw,
)

from redsun.experimental import (
    Alias,
    AsDevice,
    AsPresenter,
    AsView,
    DevicesOf,
    Placement,
    Session,
)
from redsun.experimental.injection import Devices


@dataclass(frozen=True)
class Somewhere(Placement):
    """Stand-in placement: the core ships none, and no frontend is named here."""


@runtime_checkable
class Resettable(Protocol):
    """Anything the session can put back to its initial state."""

    def reset(self) -> None: ...


class Motor:
    """Presenter that can be reset."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.resets = 0

    def reset(self) -> None:
        self.resets += 1


class Detector:
    """Another one, so the answer has more than one entry."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.resets = 0

    def reset(self) -> None:
        self.resets += 1


class Readout:
    """Component that cannot be reset, so it stays out of the answer."""

    def __init__(self, name: str) -> None:
        self.name = name


class Resetter:
    """Presenter driving every resettable component in the session."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.resettable: Mapping[str, Resettable] = {}

    def setup(self, resettable: Mapping[str, Resettable]) -> None:
        self.resettable = resettable

    def reset_all(self) -> None:
        for component in self.resettable.values():
            component.reset()


@runtime_checkable
class Linkable(Protocol):
    """A viewer whose camera another viewer can drive."""

    name: str

    def apply_camera(self, zoom: float) -> None: ...


class ImageView:
    """Peer component: it both offers the capability and asks about it."""

    placement: Placement = Somewhere()

    def __init__(self, name: str) -> None:
        self.name = name
        self.peers: Mapping[str, Linkable] = {}
        self.zoom = 1.0
        self.linked_to: str | None = None

    def setup(self, peers: Mapping[str, Linkable]) -> None:
        self.peers = peers

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

    def __init__(self, name: str) -> None:
        self.name = name
        self.resettable: Mapping[str, Resettable] = {}
        self.resets = 0

    def setup(self, resettable: Mapping[str, Resettable]) -> None:
        self.resettable = resettable

    def reset(self) -> None:
        self.resets += 1

    def reset_all(self) -> None:
        for component in self.resettable.values():
            component.reset()


class Loose:
    """Its reset takes an argument the protocol does not permit passing."""

    def __init__(self, name: str) -> None:
        self.name = name

    def reset(self, hard: bool) -> None: ...


class Renamed:
    """Its parameter name differs, so a keyword call would fail."""

    def __init__(self, name: str) -> None:
        self.name = name

    def apply_camera(self, factor: float) -> None: ...


class Tolerant:
    """An extra defaulted parameter still accepts every permitted call."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.zoom = 1.0

    def apply_camera(self, zoom: float, smooth: bool = False) -> None:
        self.zoom = zoom


class RoiWidget:
    """Asks for the one camera in the session and drives it."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.camera: Linkable | None = None

    def setup(self, camera: Linkable) -> None:
        self.camera = camera

    def zoom_to(self, zoom: float) -> None:
        assert self.camera is not None
        self.camera.apply_camera(zoom)


class MaybeWidget:
    """Asks for a camera it can do without."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.camera: Linkable | None = None

    def setup(self, camera: Linkable | None = None) -> None:
        self.camera = camera


class ImageViewAsking:
    """Offers Linkable and asks for the one component offering it."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.peer: Linkable | None = None

    def setup(self, peer: Linkable) -> None:
        self.peer = peer

    def apply_camera(self, zoom: float) -> None: ...


class Camera:
    """The single component satisfying Linkable."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.zoom = 1.0

    def apply_camera(self, zoom: float) -> None:
        self.zoom = zoom


@runtime_checkable
class Countable(Protocol):
    """Satisfied only by an attribute assigned in ``__init__``."""

    count: int

    def bump(self) -> None: ...


class Counter:
    """Its ``count`` exists only once constructed."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.count = 0

    def bump(self) -> None:
        self.count += 1


class Forgetful:
    """Passes the class-level check but never assigns ``count``."""

    def __init__(self, name: str) -> None:
        self.name = name

    def bump(self) -> None: ...


class NeedsCount:
    """Asks for the one countable component."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.counter: Countable | None = None

    def setup(self, counter: Countable) -> None:
        self.counter = counter


@runtime_checkable
class Movable(Protocol):
    """A device that can be told where to go, as ``bluesky`` moves it."""

    def set(self, value: float) -> AsyncStatus[None]: ...


class Stage(StandardReadable):
    """Device answering the device census, moving its position signal."""

    def __init__(self, name: str) -> None:
        with self.add_children_as_readables(StandardReadableFormat.HINTED_SIGNAL):
            self.position = soft_signal_rw(float, units="mm")
        super().__init__(name=name)

    @AsyncStatus.wrap
    async def set(self, value: float) -> None:
        await self.position.set(value)


class Shutter(StandardReadable):
    """Device that opens and closes but cannot move, so it stays out of the answer."""

    def __init__(self, name: str) -> None:
        with self.add_children_as_readables(StandardReadableFormat.CONFIG_SIGNAL):
            self.open = soft_signal_rw(bool)
        super().__init__(name=name)


class MotorPresenter:
    """Presenter reading the device census while it is built."""

    def __init__(self, name: str, *, motors: DevicesOf[Movable]) -> None:
        self.name = name
        self.motors = motors
        self.names = sorted(motors)


class AsksBoth:
    """Asks both censuses, which are answered over different populations."""

    def __init__(self, name: str, *, motors: DevicesOf[Movable]) -> None:
        self.name = name
        self.motors = motors
        self.resettable: Mapping[str, Resettable] = {}

    def setup(self, resettable: Mapping[str, Resettable]) -> None:
        self.resettable = resettable


class MisshapenDevices:
    """Presenter carrying the device marker on the wrong shape."""

    def __init__(
        self, name: str, *, wrong: Annotated[list[Movable], Devices()]
    ) -> None:
        self.name = name


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

    def __init__(self, name: str) -> None:
        self.name = name

    def show(self) -> None: ...


class WantsTheCanvas:
    """A presenter asking for the one displayable, which is a view."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.canvas: Displayable | None = None

    def setup(self, canvas: Displayable) -> None:
        self.canvas = canvas


class BackwardsQuestionApp(Session):
    ctrl: AsPresenter[WantsTheCanvas]
    canvas: AsView[Canvas]


class BrokenCamera:
    """The one component satisfying `Linkable`, which cannot be built."""

    def __init__(self, name: str) -> None:
        raise RuntimeError("no camera")

    def apply_camera(self, zoom: float) -> None: ...


class AsksAboutLinkables:
    """Holds the census of `Linkable`, so it can be read after the build."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.peers: Mapping[str, Linkable] = {}

    def setup(self, peers: Mapping[str, Linkable]) -> None:
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
    rejected = app.rejected(Resettable)
    assert set(rejected) == {"loose"}
    assert "cannot be called as reset()" in rejected["loose"][0]


def test_a_component_missing_every_member_is_not_a_near_miss(
    build: BuildSession,
) -> None:
    """Only components that nearly match are worth reporting."""
    app = build(App)
    assert app.rejected(Resettable) == {}


@pytest.mark.parametrize(
    ("session", "error", "match"),
    [
        pytest.param(
            NoneApp, TypeError, "nothing in the session does", id="one-answered-by-none"
        ),
        pytest.param(
            TwoApp,
            TypeError,
            "but 2 do, from 'camera', 'spare'",
            id="one-answered-by-two",
        ),
        pytest.param(
            SelfApp,
            TypeError,
            "nothing in the session does",
            id="one-answered-by-the-asker",
        ),
        pytest.param(
            MaybeTwoApp,
            TypeError,
            "but 2 do, from 'camera', 'spare'",
            id="maybe-answered-by-two",
        ),
        pytest.param(
            RenamedApp,
            TypeError,
            "nothing in the session does",
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
            "'counter': 'count' is missing",
            id="data-member-never-assigned",
        ),
        pytest.param(
            BackwardsQuestionApp,
            TypeError,
            "knows nothing about a view",
            id="one-answered-by-a-later-layer",
        ),
    ],
)
def test_the_session_refuses_to_build(
    session: type[Session], error: type[Exception], match: str
) -> None:
    with pytest.raises(error, match=match):
        session().build()


def test_one_arrives_built(build: BuildSession) -> None:
    """The one answer arrives built, ready to drive."""
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
    """The match reads the instance, where ``__init__`` assigned the member."""
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


def test_a_component_asking_only_for_devices_is_not_warned_about(
    build: BuildSession, caplog: pytest.LogCaptureFixture
) -> None:
    """Asking for devices is asking for something, whoever answers it."""
    build(DeviceApp)
    assert "'motors' shares nothing" not in caplog.text


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


def test_the_census_leaves_out_a_component_that_failed(
    build: BuildSession,
) -> None:
    """A component asks what the session holds, not what it declared."""
    app = build(CensusReaderApp)
    assert set(app.reader.peers) == {"camera"}


def test_the_one_answer_failing_leaves_the_asker_unset(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Exactly one was demanded, and the session holds none once it failed."""
    with caplog.at_level(logging.WARNING, logger="redsun"):
        app = BrokenOneApp().build()
    try:
        assert app.is_built
        assert set(app.presenters) == {"roi"}
        assert app.roi.camera is None
        assert "Failed to set up presenter 'roi': 'broken' was not built" in caplog.text
    finally:
        app.shutdown()


def test_an_optional_answer_failing_leaves_the_asker_without_one(
    build: BuildSession,
) -> None:
    """At most one was asked for, and the session ended up holding none."""
    app = build(BrokenMaybeApp)
    assert set(app.presenters) == {"widget"}
    assert app.widget.camera is None


def test_a_device_census_on_the_wrong_shape_skips_the_component(
    build: BuildSession, caplog: pytest.LogCaptureFixture
) -> None:
    app = build(MisshapenDevicesApp)

    assert "broken" not in app.presenters
    assert "Write 'DevicesOf[P]'" in caplog.text
