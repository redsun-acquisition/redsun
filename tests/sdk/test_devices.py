"""Tests for reading the axes, limits and configuration of a device."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import numpy as np
import pytest
from ophyd_async.core import (
    MovableLogic,
    StandardMovable,
    StandardReadable,
    StandardReadableFormat,
    soft_signal_rw,
)

from redsun.utils.devices import describe_axis, find_axes, limits
from tests.sdk.mocks import SoftAxis, Stage, TwinStage

if TYPE_CHECKING:
    from bluesky.protocols import Location


class ThermalAxis(StandardReadable, StandardMovable[float]):
    """An axis reading a temperature beside its hinted position."""

    def __init__(self, name: str = "") -> None:
        with self.add_children_as_readables():
            self.temperature = soft_signal_rw(float, 21.0, units="C", precision=1)
        with self.add_children_as_readables(StandardReadableFormat.HINTED_SIGNAL):
            self.position = soft_signal_rw(float, 0.0, units="um", precision=-1)
        super().__init__(name=name)

    @property
    def movable_logic(self) -> MovableLogic[float]:
        """Setpoint and readback of the axis, which are one signal."""
        return MovableLogic(setpoint=self.position, readback=self.position)


class Float32Axis(SoftAxis):
    """A soft axis reporting its position as a numpy float32."""

    async def locate(self) -> Location[float]:
        """Return the position as numpy float32 values."""
        location = await super().locate()
        reported: Any = {
            "setpoint": np.float32(location["setpoint"]),
            "readback": np.float32(location["readback"]),
        }
        return cast("Location[float]", reported)


class OuterAxis(SoftAxis):
    """A soft axis holding a finer axis of its own."""

    def __init__(self, name: str = "") -> None:
        self.fine = SoftAxis()
        super().__init__(name=name)


class Carrier(StandardReadable):
    """A device holding one axis that holds another."""

    def __init__(self, name: str) -> None:
        self.coarse = OuterAxis()
        super().__init__(name=name)


async def test_the_axes_of_a_device_are_its_movable_descendants() -> None:
    """Find the axes inside a `DeviceMap`, keyed by name, and skip plain signals."""
    stage = Stage("stage")
    await stage.connect(mock=False)

    axes = find_axes(stage)

    assert set(axes) == {"x", "theta"}
    assert axes["x"] is stage.axis["x"]
    assert axes["theta"] is stage.axis["theta"]


async def test_a_device_that_moves_itself_is_its_one_axis() -> None:
    """Return a movable device as its own axis, under its name."""
    axis = SoftAxis("focus")
    await axis.connect(mock=False)

    axes = find_axes(axis)

    assert list(axes) == ["focus"]
    assert axes["focus"] is axis


async def test_axes_sharing_a_name_are_keyed_by_their_path() -> None:
    """Key two axes named `x` by their dotted paths."""
    twin = TwinStage("twin")
    await twin.connect(mock=False)

    assert set(find_axes(twin)) == {"left.x", "right.x"}


def test_a_signal_is_never_an_axis() -> None:
    """Find no axis in a signal, though a writable signal can be moved."""
    assert find_axes(soft_signal_rw(float, 0.0, name="exposure")) == {}


@pytest.mark.parametrize(
    ("descriptor", "expected"),
    [
        pytest.param(
            {"limits": {"control": {"low": -1.0, "high": 2.0}}},
            (-1.0, 2.0),
            id="control",
        ),
        pytest.param(
            {"limits": {"display": {"low": 0.0, "high": 9.0}}}, (0.0, 9.0), id="display"
        ),
        pytest.param(
            {"limits": {"control": {"low": 0.0, "high": 0.0}}},
            (None, None),
            id="epics-none",
        ),
        pytest.param(
            {"limits": {"control": {"high": 5.0}}}, (None, 5.0), id="one-bound"
        ),
        pytest.param({}, (None, None), id="no-limits"),
        pytest.param(
            {
                "limits": {
                    "control": {"low": 1.0, "high": 2.0},
                    "display": {"low": 0.0, "high": 9.0},
                }
            },
            (1.0, 2.0),
            id="control-first",
        ),
        pytest.param(
            {"limits": {"control": {"low": 3.0, "high": 1.0}}},
            (None, None),
            id="reversed",
        ),
    ],
)
def test_limits_are_read_from_a_descriptor(
    descriptor: dict[str, object], expected: tuple[float | None, float | None]
) -> None:
    """Read control limits, else display ones, and count a 0-0 pair as none."""
    assert limits(descriptor) == expected


async def test_the_walk_stops_at_an_axis() -> None:
    """Find an axis holding a finer axis, and not the finer axis inside it."""
    carrier = Carrier("carrier")
    await carrier.connect(mock=False)

    assert list(find_axes(carrier)) == ["coarse"]


async def test_an_axis_is_described_by_its_hinted_entry() -> None:
    """Read units from the hinted entry, and drop a negative precision."""
    axis = ThermalAxis("focus")
    await axis.connect(mock=False)

    info = await describe_axis(axis)

    assert (info.units, info.precision) == ("um", None)
    assert info.key == axis.position.name


async def test_a_numpy_position_is_a_number() -> None:
    """Describe an axis whose position is a numpy float32."""
    axis = Float32Axis("focus")
    await axis.connect(mock=False)

    info = await describe_axis(axis)

    assert info.position == pytest.approx(0.0)
