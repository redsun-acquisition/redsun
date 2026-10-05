"""Tests for the positioner presenter."""

from __future__ import annotations

import asyncio
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest
from ophyd_async.core import (
    MovableLogic,
    StandardMovable,
    StandardReadable,
    StandardReadableFormat,
    set_mock_attr,
    soft_signal_rw,
)

from redsun.presenter import DescribesAxes, PositionerPresenter
from tests.sdk.mocks import (
    BrokenConfigAxis,
    HangingAxis,
    LaggingAxis,
    LimitedAxis,
    MockDetector,
    QuietStage,
    SoftAxis,
    Stage,
    StuckStage,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Generator

    from event_model import DataKey


class FilterWheel(StandardReadable, StandardMovable[str]):
    """An axis whose position is the name of a filter."""

    def __init__(self, name: str = "") -> None:
        with self.add_children_as_readables(StandardReadableFormat.HINTED_SIGNAL):
            self.position = soft_signal_rw(str, "red")
        super().__init__(name=name)

    @property
    def movable_logic(self) -> MovableLogic[str]:
        """Setpoint and readback of the wheel, which are one signal."""
        return MovableLogic(setpoint=self.position, readback=self.position)


@dataclass(eq=False, kw_only=True)
class KeepOut(PositionerPresenter):
    """A positioner refusing x targets from 4 to 6."""

    def check(self, device: str, axis: str, target: float) -> None:
        """Refuse the keep-out zone, after the default checks."""
        super().check(device, axis, target)
        if axis == "x" and 4.0 <= target <= 6.0:
            raise ValueError(f"x {target} is in the keep-out zone")


@pytest.fixture
async def stage() -> Stage:
    device = Stage("stage")
    await device.connect(mock=False)
    return device


@pytest.fixture
def presenter(stage: Stage) -> Generator[PositionerPresenter, None, None]:
    positioner = PositionerPresenter("positioner", devices={"stage": stage})
    yield positioner
    positioner.shutdown()


async def started(presenter: PositionerPresenter, device: str) -> None:
    """Wait until *device* starts moving."""
    moving = asyncio.Event()

    def note(name: str, now: bool) -> None:
        if now and name == device:
            moving.set()

    presenter.sig_moving.connect(note)
    await asyncio.wait_for(moving.wait(), 2.0)


async def position(axis: SoftAxis) -> float:
    """Return where *axis* reads back."""
    return (await axis.locate())["readback"]


async def test_the_axes_are_described_and_followed(
    presenter: PositionerPresenter, stage: Stage
) -> None:
    """Describe each axis, then relay every readback it reports."""
    seen: list[tuple[str, str, float]] = []
    presenter.sig_readback.connect(lambda *args: seen.append(args))

    await stage.axis["x"].set(2.5)

    x = presenter.axes["stage"]["x"]

    assert isinstance(presenter, DescribesAxes)
    assert set(presenter.axes["stage"]) == {"x", "theta"}
    assert (x.position, x.units, x.precision, x.stoppable) == (0.0, "um", 3, True)
    assert set(x.configuration) == {
        stage.axis["x"].velocity.name,
        stage.axis["x"].resolution.name,
    }
    assert ("stage", "x", 2.5) in seen


async def test_a_step_moves_from_the_readback(
    presenter: PositionerPresenter, stage: Stage
) -> None:
    """Move an axis by a step, bracketed by the moving state."""
    states: list[tuple[str, bool]] = []
    presenter.sig_moving.connect(lambda *args: states.append(args))

    await presenter.move("stage", "x", 1.5)
    await presenter.move("stage", "x", 1.5)

    assert await position(stage.axis["x"]) == pytest.approx(3.0)
    assert states == [("stage", True), ("stage", False)] * 2


async def test_a_step_asked_while_the_device_moves_is_skipped(
    presenter: PositionerPresenter, stage: Stage
) -> None:
    """Skip a step for a busy device, and wait for it with a go-to."""
    gate = asyncio.Event()
    stage.axis["x"].logic.gate = gate
    first = asyncio.create_task(presenter.move("stage", "x", 1.0))
    await started(presenter, "stage")

    await presenter.move("stage", "x", 1.0)
    going = asyncio.create_task(presenter.move_to("stage", {"theta": 4.0}))
    await asyncio.sleep(0)
    assert not going.done()
    gate.set()
    await asyncio.gather(first, going)

    assert await position(stage.axis["x"]) == pytest.approx(1.0)
    assert await position(stage.axis["theta"]) == pytest.approx(4.0)


async def test_a_go_to_moves_every_axis_it_names(
    presenter: PositionerPresenter, stage: Stage
) -> None:
    """Move the named axes of a device to the given positions."""
    await presenter.move_to("stage", {"x": 7.0, "theta": -1.0})

    assert await position(stage.axis["x"]) == pytest.approx(7.0)
    assert await position(stage.axis["theta"]) == pytest.approx(-1.0)


async def test_a_failed_move_is_reported_and_ends_the_moving_state(
    presenter: PositionerPresenter, stage: Stage
) -> None:
    """Report a move that raises, then leave the device idle."""
    stage.axis["x"].logic.refuse = "out of range"
    failures: list[tuple[str, str]] = []
    states: list[tuple[str, bool]] = []
    presenter.sig_failed.connect(lambda *args: failures.append(args))
    presenter.sig_moving.connect(lambda *args: states.append(args))

    await presenter.move("stage", "x", 1.0)

    assert failures == [("stage", "out of range")]
    assert states[-1] == ("stage", False)


async def test_only_devices_with_axes_and_included_are_kept(stage: Stage) -> None:
    """Keep the included devices that have axes, and ignore the rest."""
    other = Stage("other")
    await other.connect(mock=False)
    detector = MockDetector("camera")
    await detector.connect(mock=False)
    positioner = PositionerPresenter(
        "positioner",
        devices={"stage": stage, "other": other, "camera": detector},
        include=["stage", "camera"],
    )

    assert set(positioner.axes) == {"stage"}
    positioner.shutdown()


async def test_stop_ends_a_move_without_a_failure(
    presenter: PositionerPresenter, stage: Stage
) -> None:
    """Stop a running move, leave the device idle and report no failure."""
    stage.axis["x"].logic.gate = asyncio.Event()
    failures: list[tuple[str, str]] = []
    states: list[tuple[str, bool]] = []
    presenter.sig_failed.connect(lambda *args: failures.append(args))
    presenter.sig_moving.connect(lambda *args: states.append(args))
    moving = asyncio.create_task(presenter.move("stage", "x", 1.0))
    await started(presenter, "stage")

    await presenter.stop("stage")
    await asyncio.wait_for(moving, 2.0)

    assert failures == []
    assert states[-1] == ("stage", False)
    assert await position(stage.axis["x"]) == pytest.approx(0.0)


async def test_stop_also_ends_a_go_to_waiting_for_the_device(
    presenter: PositionerPresenter, stage: Stage
) -> None:
    """Drop a go-to queued behind the move a stop ends."""
    stage.axis["x"].logic.gate = asyncio.Event()
    moving = asyncio.create_task(presenter.move_to("stage", {"x": 5.0}))
    await started(presenter, "stage")
    waiting = asyncio.create_task(presenter.move_to("stage", {"theta": 9.0}))
    await asyncio.sleep(0)

    await presenter.stop("stage")
    await asyncio.wait_for(asyncio.gather(moving, waiting), 2.0)

    assert await position(stage.axis["theta"]) == pytest.approx(0.0)


async def test_an_axis_without_a_numeric_position_is_left_out(
    stage: Stage, caplog: pytest.LogCaptureFixture
) -> None:
    """Leave out, with a warning, an axis whose position is not a number."""
    wheel = FilterWheel("wheel")
    await wheel.connect(mock=False)

    positioner = PositionerPresenter(
        "positioner", devices={"stage": stage, "wheel": wheel}
    )

    assert set(positioner.axes) == {"stage"}
    assert "wheel" in caplog.text
    positioner.shutdown()


async def test_the_configuration_marks_what_cannot_be_written(
    presenter: PositionerPresenter, stage: Stage
) -> None:
    """List each axis' configuration, the read-only entries marked."""
    descriptors = presenter.configuration.descriptors
    readings = presenter.configuration.readings
    velocity = stage.axis["x"].velocity.name
    resolution = stage.axis["x"].resolution.name

    assert not descriptors[velocity]["source"].endswith(":readonly")
    assert descriptors[resolution]["source"].endswith(":readonly")
    assert readings[velocity]["value"] == 1.0


async def test_a_configuration_write_reports_what_the_signal_reads(
    presenter: PositionerPresenter, stage: Stage
) -> None:
    """Report the value read back after a write, and after a refused one."""
    seen: list[tuple[str, object]] = []
    presenter.sig_configuration.connect(lambda *args: seen.append(args))
    key = stage.axis["x"].velocity.name

    await presenter.configure(key, 2.5)
    written = seen[-1]
    seen.clear()
    await presenter.configure(key, "fast")

    assert (written, seen) == ((key, 2.5), [(key, 2.5)])


async def test_a_configuration_change_made_elsewhere_is_reported_until_shutdown(
    presenter: PositionerPresenter, stage: Stage
) -> None:
    """Report configuration values changed on the device, until shut down."""
    seen: list[tuple[str, object]] = []
    presenter.sig_configuration.connect(lambda *args: seen.append(args))
    axis = stage.axis["x"]

    await axis.velocity.set(3.0)
    axis.set_resolution(0.5)
    reported = list(seen)
    presenter.shutdown()
    await axis.velocity.set(4.0)

    assert reported == [(axis.velocity.name, 3.0), (axis.resolution.name, 0.5)]
    assert seen == reported


async def test_limits_come_from_the_readback_descriptor() -> None:
    """Read an axis' limits from the descriptor of its readback."""
    axis = LimitedAxis("focus")
    await axis.connect(mock=False)
    positioner = PositionerPresenter("positioner", devices={"focus": axis})

    assert positioner.axes["focus"]["focus"].limits == (-5.0, 5.0)
    positioner.shutdown()


async def test_limits_follow_a_configuration_write() -> None:
    """Report and apply the limits a configuration write moves."""
    axis = LimitedAxis("focus")
    await axis.connect(mock=False)
    positioner = PositionerPresenter("positioner", devices={"focus": axis})
    seen: list[tuple[str, str, float | None, float | None]] = []
    positioner.sig_limits.connect(lambda *args: seen.append(args))

    await positioner.configure(axis.offset.name, 10.0)
    await positioner.move_to("focus", {"focus": 12.0})

    assert seen == [("focus", "focus", 5.0, 15.0)]
    assert positioner.axes["focus"]["focus"].limits == (5.0, 15.0)
    assert await position(axis) == pytest.approx(12.0)
    positioner.shutdown()


async def test_limits_changed_on_the_device_hold_at_the_next_move() -> None:
    """Refuse a target inside the old limits once the device has moved them."""
    axis = LimitedAxis("focus")
    await axis.connect(mock=False)
    positioner = PositionerPresenter("positioner", devices={"focus": axis})
    seen: list[tuple[str, str, float | None, float | None]] = []
    positioner.sig_limits.connect(lambda *args: seen.append(args))
    failures: list[tuple[str, str]] = []
    positioner.sig_failed.connect(lambda *args: failures.append(args))

    await axis.offset.set(10.0)
    await positioner.move_to("focus", {"focus": 3.0})

    assert await position(axis) == pytest.approx(0.0)
    assert seen == [("focus", "focus", 5.0, 15.0)]
    assert [device for device, _ in failures] == ["focus"]
    positioner.shutdown()


async def test_steps_add_up_on_the_setpoint_and_restart_from_the_readback_after_a_stop() -> (
    None
):
    """Step from the setpoint after a move, and from the readback after a stop."""
    axis = LaggingAxis("focus")
    await axis.connect(mock=False)
    positioner = PositionerPresenter("positioner", devices={"focus": axis})

    await positioner.move("focus", "focus", 1.0)
    await positioner.move("focus", "focus", 1.0)
    after_steps = await axis.setpoint.get_value()
    await positioner.stop("focus")
    await positioner.move("focus", "focus", 1.0)

    assert after_steps == pytest.approx(2.0)
    assert await axis.setpoint.get_value() == pytest.approx(1.996 + 1.0)
    positioner.shutdown()


async def test_a_device_moves_again_after_a_stop(
    presenter: PositionerPresenter, stage: Stage
) -> None:
    """Move a device that was stopped while idle."""
    await presenter.stop("stage")

    await presenter.move("stage", "x", 2.0)

    assert await position(stage.axis["x"]) == pytest.approx(2.0)


async def test_stop_reaches_every_axis_when_one_fails() -> None:
    """Stop the other axes when one refuses, and report the refusal."""
    stage = StuckStage("stage")
    await stage.connect(mock=False)
    positioner = PositionerPresenter("positioner", devices={"stage": stage})
    failures: list[tuple[str, str]] = []
    positioner.sig_failed.connect(lambda *args: failures.append(args))
    stage.axis["x"].logic.gate = asyncio.Event()
    moving = asyncio.create_task(positioner.move("stage", "x", 1.0))
    await started(positioner, "stage")

    await positioner.stop("stage")
    await asyncio.wait_for(moving, 2.0)

    assert await position(stage.axis["x"]) == pytest.approx(0.0)
    assert [device for device, _ in failures] == ["stage"]
    assert "stop write timed out" in failures[0][1]
    positioner.shutdown()


async def test_stop_ends_a_go_to_between_its_axes() -> None:
    """Leave the next axis of a go-to unmoved when the first ends quietly on stop."""
    stage = QuietStage("quiet")
    await stage.connect(mock=False)
    positioner = PositionerPresenter("positioner", devices={"quiet": stage})
    going = asyncio.create_task(positioner.move_to("quiet", {"a": 1.0, "b": 2.0}))
    await started(positioner, "quiet")

    await positioner.stop("quiet")
    await asyncio.wait_for(going, 2.0)

    assert stage.a.started
    assert not stage.b.started
    positioner.shutdown()


@pytest.mark.parametrize("target", [9.0, math.nan, math.inf])
async def test_a_target_outside_the_limits_or_not_finite_is_refused(
    target: float,
) -> None:
    """Refuse a go-to beyond the limits of the axis, or to a value not finite."""
    axis = LimitedAxis("focus")
    await axis.connect(mock=False)
    positioner = PositionerPresenter("positioner", devices={"focus": axis})
    failures: list[tuple[str, str]] = []
    positioner.sig_failed.connect(lambda *args: failures.append(args))

    await positioner.move_to("focus", {"focus": target})

    assert await position(axis) == pytest.approx(0.0)
    assert [device for device, _ in failures] == ["focus"]
    positioner.shutdown()


async def test_a_subclass_check_guards_steps_as_well_as_go_tos(stage: Stage) -> None:
    """Refuse a step into a zone a subclass forbids, as a go-to is refused."""
    positioner = KeepOut("positioner", devices={"stage": stage})

    await positioner.move_to("stage", {"x": 3.0})
    await positioner.move("stage", "x", 2.0)
    await positioner.move_to("stage", {"x": 5.0})

    assert await position(stage.axis["x"]) == pytest.approx(3.0)
    positioner.shutdown()


async def test_an_axis_whose_configuration_cannot_be_read_is_left_out(
    stage: Stage, caplog: pytest.LogCaptureFixture
) -> None:
    """Leave out an axis that fails after it was described, and stop following it."""
    broken = BrokenConfigAxis("broken")
    await broken.connect(mock=False)
    positioner = PositionerPresenter(
        "positioner", devices={"stage": stage, "broken": broken}
    )
    seen: list[str] = []
    positioner.sig_readback.connect(lambda device, axis, value: seen.append(device))

    await broken.set(1.0)

    assert set(positioner.axes) == {"stage"}
    assert "broken" in caplog.text
    assert seen == []
    positioner.shutdown()


async def test_an_axis_that_never_answers_is_left_out_after_the_timeout(
    stage: Stage,
) -> None:
    """Leave out an axis still silent after the timeout, and build the rest."""
    hanging = HangingAxis("hanging")
    await hanging.connect(mock=False)

    positioner = PositionerPresenter(
        "positioner", devices={"stage": stage, "hanging": hanging}, timeout=0.2
    )

    assert set(positioner.axes) == {"stage"}
    positioner.shutdown()


async def test_an_unknown_name_in_include_is_reported(
    stage: Stage, caplog: pytest.LogCaptureFixture
) -> None:
    """Warn about a name in `include` that names no device of the session."""
    positioner = PositionerPresenter(
        "positioner", devices={"stage": stage}, include=["stage", "stgae"]
    )

    assert "stgae" in caplog.text
    positioner.shutdown()


async def test_a_held_device_takes_no_hand_move_or_configuration(
    presenter: PositionerPresenter, stage: Stage
) -> None:
    """Refuse moves and configuration writes for a device a plan holds."""
    seen: list[tuple[str, object]] = []
    presenter.sig_configuration.connect(lambda *args: seen.append(args))
    key = stage.axis["x"].velocity.name

    presenter.set_locked(frozenset({"stage"}))
    await presenter.move_to("stage", {"x": 3.0})
    await presenter.configure(key, 9.0)

    assert await position(stage.axis["x"]) == pytest.approx(0.0)
    assert await stage.axis["x"].velocity.get_value() == pytest.approx(1.0)
    assert seen == [(key, 1.0)]


async def test_a_go_to_waiting_when_a_plan_takes_the_device_is_dropped(
    presenter: PositionerPresenter, stage: Stage
) -> None:
    """Drop a go-to queued behind a move once a plan holds the device."""
    gate = asyncio.Event()
    stage.axis["x"].logic.gate = gate
    moving = asyncio.create_task(presenter.move_to("stage", {"x": 1.0}))
    await started(presenter, "stage")
    waiting = asyncio.create_task(presenter.move_to("stage", {"theta": 9.0}))
    await asyncio.sleep(0)

    presenter.set_locked(frozenset({"stage"}))
    gate.set()
    await asyncio.wait_for(asyncio.gather(moving, waiting), 2.0)

    assert await position(stage.axis["theta"]) == pytest.approx(0.0)


async def test_shutdown_stops_a_running_move_and_the_readbacks(stage: Stage) -> None:
    """Stop a move in progress at shutdown, and relay no readback after it."""
    positioner = PositionerPresenter("positioner", devices={"stage": stage})
    seen: list[float] = []
    positioner.sig_readback.connect(lambda device, axis, value: seen.append(value))
    stage.axis["x"].logic.gate = asyncio.Event()
    moving = asyncio.create_task(positioner.move("stage", "x", 1.0))
    await started(positioner, "stage")

    await asyncio.to_thread(positioner.shutdown)
    await asyncio.wait_for(moving, 2.0)
    await stage.axis["theta"].set(4.0)

    assert await position(stage.axis["x"]) == pytest.approx(0.0)
    assert 4.0 not in seen


@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda p, stage: p.move("absent", "x", 1.0), id="move"),
        pytest.param(lambda p, stage: p.move_to("absent", {"x": 1.0}), id="move-to"),
        pytest.param(lambda p, stage: p.stop("absent"), id="stop"),
        pytest.param(lambda p, stage: p.configure("absent-key", 1.0), id="unknown-key"),
        pytest.param(
            lambda p, stage: p.configure(stage.axis["x"].resolution.name, 1.0),
            id="read-only-key",
        ),
    ],
)
async def test_an_unknown_device_or_key_is_refused(
    presenter: PositionerPresenter,
    stage: Stage,
    call: Callable[[PositionerPresenter, Stage], Awaitable[None]],
) -> None:
    """Raise `KeyError` for a device the presenter does not hold, or a key it cannot write."""
    with pytest.raises(KeyError):
        await call(presenter, stage)


async def test_a_failing_receiver_does_not_reach_the_device(
    presenter: PositionerPresenter, stage: Stage, caplog: pytest.LogCaptureFixture
) -> None:
    """Log a receiver that raises on a readback or a configuration change."""

    def fail(*args: object) -> None:
        raise RuntimeError("receiver broke")

    presenter.sig_readback.connect(fail)
    presenter.sig_configuration.connect(fail)

    await stage.axis["x"].set(1.0)
    await stage.axis["x"].velocity.set(3.0)

    assert "Relaying a readback" in caplog.text
    assert "Relaying a configuration value" in caplog.text


async def test_an_axis_checking_its_own_targets_is_not_described_per_step() -> None:
    """Leave the limits of each step to an axis that checks its own targets."""
    axis = LimitedAxis("focus")
    await axis.connect(mock=False)
    positioner = PositionerPresenter("positioner", devices={"focus": axis})
    describe = axis.describe
    calls: list[None] = []

    async def counted() -> dict[str, DataKey]:
        calls.append(None)
        return await describe()

    set_mock_attr(axis, "describe", counted)
    for _ in range(3):
        await positioner.move("focus", "focus", 1.0)

    assert await position(axis) == pytest.approx(3.0)
    assert calls == []
    positioner.shutdown()


async def test_a_refusal_on_old_limits_reads_the_new_ones() -> None:
    """Take a target the device's new limits allow on the try after a refusal."""
    axis = LimitedAxis("focus")
    await axis.connect(mock=False)
    positioner = PositionerPresenter("positioner", devices={"focus": axis})

    await axis.offset.set(10.0)
    await positioner.move_to("focus", {"focus": 12.0})
    refused_at = await position(axis)
    await positioner.move_to("focus", {"focus": 12.0})

    assert refused_at == pytest.approx(0.0)
    assert await position(axis) == pytest.approx(12.0)
    positioner.shutdown()


async def test_a_device_that_is_its_own_axis_is_named_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Log a move of a device that is its own axis under its name alone."""
    axis = SoftAxis("focus")
    await axis.connect(mock=False)
    positioner = PositionerPresenter("positioner", devices={"focus": axis})

    await positioner.move_to("focus", {"focus": 2.0})

    assert "Moving focus to 2.0" in caplog.text
    positioner.shutdown()


async def test_cancelling_the_slot_cancels_the_move(
    presenter: PositionerPresenter, stage: Stage
) -> None:
    """Pass a cancellation of the slot on, leaving the axis where it was."""
    gate = asyncio.Event()
    stage.axis["x"].logic.gate = gate
    moving = asyncio.create_task(presenter.move("stage", "x", 1.0))
    await started(presenter, "stage")

    moving.cancel()
    with pytest.raises(asyncio.CancelledError):
        await moving
    gate.set()
    await asyncio.sleep(0.05)

    assert await position(stage.axis["x"]) == pytest.approx(0.0)
