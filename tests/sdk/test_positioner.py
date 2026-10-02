"""Tests for the positioner presenter."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest
from ophyd_async.core import (
    MovableLogic,
    StandardMovable,
    StandardReadable,
    StandardReadableFormat,
    soft_signal_rw,
)

from redsun.presenter import AxisInfo, DescribesAxes, PositionerPresenter
from tests.sdk.mocks import LimitedAxis, MockDetector, SoftAxis, Stage

if TYPE_CHECKING:
    from collections.abc import Generator


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

    assert isinstance(presenter, DescribesAxes)
    assert presenter.axes() == {
        "stage": {
            "x": AxisInfo(position=0.0, units="um", precision=3, stoppable=True),
            "theta": AxisInfo(position=0.0, units="um", precision=3, stoppable=True),
        }
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
    await asyncio.sleep(0.05)

    await presenter.move("stage", "x", 1.0)
    going = asyncio.create_task(presenter.move_to("stage", {"theta": 4.0}))
    await asyncio.sleep(0.05)
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

    assert set(positioner.axes()) == {"stage"}
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
    await asyncio.sleep(0.05)

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
    await asyncio.sleep(0.05)
    waiting = asyncio.create_task(presenter.move_to("stage", {"theta": 9.0}))
    await asyncio.sleep(0.05)

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

    assert set(positioner.axes()) == {"stage"}
    assert "wheel" in caplog.text
    positioner.shutdown()


async def test_the_configuration_marks_what_cannot_be_written(
    presenter: PositionerPresenter, stage: Stage
) -> None:
    """List each axis' configuration, the read-only entries marked."""
    descriptors, readings = presenter.configuration()
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
    await presenter.configure(key, "fast")

    assert seen == [(key, 2.5), (key, 2.5)]


async def test_limits_come_from_the_readback_descriptor() -> None:
    """Read an axis' limits from the descriptor of its readback."""
    axis = LimitedAxis("focus")
    await axis.connect(mock=False)
    positioner = PositionerPresenter("positioner", devices={"focus": axis})

    assert positioner.axes()["focus"]["focus"].limits == (-5.0, 5.0)
    positioner.shutdown()


def test_a_device_it_does_not_hold_is_refused(presenter: PositionerPresenter) -> None:
    """Raise `KeyError` for a device the presenter does not hold."""
    with pytest.raises(KeyError):
        asyncio.run(presenter.move("absent", "x", 1.0))
