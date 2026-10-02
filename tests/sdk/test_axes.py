"""Tests for finding the axes of a device."""

from __future__ import annotations

from ophyd_async.core import soft_signal_rw

from redsun.presenter import find_axes
from tests.sdk.mocks import SoftAxis, Stage, TwinStage


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
