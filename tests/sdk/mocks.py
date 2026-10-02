"""Mock classes for redsun SDK tests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from ophyd_async.core import (
    DeviceMap,
    MovableLogic,
    SignalRW,
    StandardMovable,
    StandardReadable,
    StandardReadableFormat,
    soft_signal_r_and_setter,
    soft_signal_rw,
)

if TYPE_CHECKING:
    from event_model import DataKey


class MockDetector(StandardReadable):
    """Mock detector device using soft signals.

    The EGU for `exposure` is embedded in the descriptor document
    (`describe()["<name>-exposure"]["units"]`), not as a separate signal.
    """

    exposure: SignalRW[float]
    integer: SignalRW[int]
    floating: SignalRW[float]

    def __init__(
        self,
        name: str,
        *,
        exposure: float = 1.0,
        exposure_units: str = "ms",
        integer: int = 0,
        floating: float = 0.0,
        **_: Any,
    ) -> None:
        with self.add_children_as_readables():
            self.exposure = soft_signal_rw(
                float, initial_value=exposure, units=exposure_units
            )
            self.integer = soft_signal_rw(int, initial_value=integer)
            self.floating = soft_signal_rw(float, initial_value=floating)
        super().__init__(name=name)


@dataclass
class GatedLogic(MovableLogic[float]):
    """Move logic that waits for `gate` and refuses `refuse` before moving."""

    gate: asyncio.Event | None = None
    refuse: str | None = None

    async def check_move(self, new_position: float) -> None:
        """Refuse every move with `refuse`, when it is set."""
        if self.refuse is not None:
            raise RuntimeError(self.refuse)

    async def move(self, new_position: float, timeout: Any) -> None:
        """Wait for `gate`, when it is set, then write the setpoint."""
        if self.gate is not None:
            await self.gate.wait()
        await self.setpoint.set(new_position)


class SoftAxis(StandardReadable, StandardMovable[float]):
    """An axis whose position is one soft signal, read back as written.

    Its configuration holds a writable `velocity` and a read-only
    `resolution`, as a motor record's does.
    """

    def __init__(
        self, name: str = "", *, units: str = "um", precision: int = 3
    ) -> None:
        with self.add_children_as_readables(StandardReadableFormat.HINTED_SIGNAL):
            self.position = soft_signal_rw(float, 0.0, units=units, precision=precision)
        with self.add_children_as_readables(StandardReadableFormat.CONFIG_SIGNAL):
            self.velocity = soft_signal_rw(float, 1.0, units=f"{units}/s")
            self.resolution, self.set_resolution = soft_signal_r_and_setter(float, 0.01)
        self.logic = GatedLogic(setpoint=self.position, readback=self.position)
        super().__init__(name=name)

    @property
    def movable_logic(self) -> MovableLogic[float]:
        """Setpoint and readback of this axis, which are one signal."""
        return self.logic


class LimitedAxis(SoftAxis):
    """A soft axis whose readback descriptor reports travel limits."""

    async def describe(self) -> dict[str, DataKey]:
        """Describe the axis, with limits of -5 and 5 on every entry."""
        described = await super().describe()
        for descriptor in described.values():
            descriptor["limits"] = {"control": {"low": -5.0, "high": 5.0}}
        return described


class Stage(StandardReadable):
    """A device holding its axes in a `DeviceMap`, plus a plain signal."""

    def __init__(self, name: str, axes: tuple[str, ...] = ("x", "theta")) -> None:
        self.axis = DeviceMap({axis: SoftAxis() for axis in axes})
        self.add_readables(list(self.axis.values()))
        with self.add_children_as_readables(StandardReadableFormat.CONFIG_SIGNAL):
            self.speed = soft_signal_rw(float, 1.0)
        super().__init__(name=name)


class TwinStage(StandardReadable):
    """A device with two groups whose axes share the name `x`."""

    def __init__(self, name: str) -> None:
        self.left = DeviceMap({"x": SoftAxis()})
        self.right = DeviceMap({"x": SoftAxis()})
        super().__init__(name=name)
