"""Simulated devices and plans for the example session."""

from __future__ import annotations

from functools import cached_property
from typing import TYPE_CHECKING

import bluesky.plan_stubs as bps
from bluesky.utils import MsgGenerator  # noqa: TC002
from ophyd_async.core import (
    DeviceMap,
    MovableLogic,
    SignalRW,
    SoftSignalBackend,
    StandardMovable,
    StandardReadable,
    StandardReadableFormat,
    soft_signal_rw,
)

from redsun.engine.plan_stubs import lock_wrapper

if TYPE_CHECKING:
    from collections.abc import Mapping

    from event_model import DataKey

    from redsun import PlanEntry

PAUSE = 0.5
"""Seconds the walk waits after each move, so a run lasts long enough to watch, pause or stop."""


class Axis(StandardReadable, StandardMovable[float]):
    """An axis moving at once to where it is sent, by itself or as part of a stage."""

    def __init__(self, name: str = "") -> None:
        with self.add_children_as_readables(StandardReadableFormat.HINTED_SIGNAL):
            self.position = soft_signal_rw(float, 0.0, units="um", precision=2)
        with self.add_children_as_readables(StandardReadableFormat.CONFIG_SIGNAL):
            self.velocity = soft_signal_rw(float, 100.0, units="um/s")
        super().__init__(name=name)

    @cached_property
    def movable_logic(self) -> MovableLogic[float]:
        """The axis' position, as what a move sets and reads back."""
        return MovableLogic(setpoint=self.position, readback=self.position)


class Stage(StandardReadable):
    """A stage with an `x` and a `y` axis."""

    def __init__(self, name: str = "") -> None:
        self.axis = DeviceMap({"x": Axis(), "y": Axis()})
        self.add_readables(list(self.axis.values()))
        super().__init__(name=name)


class LimitedBackend(SoftSignalBackend[float]):
    """Keeps a value in memory and reports limits, as a hardware record does."""

    async def get_datakey(self, source: str) -> DataKey:
        """Return the signal's description, with control limits of 0 and 50."""
        key = await super().get_datakey(source)
        key["limits"] = {"control": {"low": 0.0, "high": 50.0}}
        return key


class Laser(StandardReadable):
    """A light that switches on and off and has an intensity from 0 to 50 mW."""

    def __init__(self, name: str = "") -> None:
        with self.add_children_as_readables():
            self.enabled = soft_signal_rw(bool, False)
            self.intensity = SignalRW(
                LimitedBackend(float, 10.0, units="mW", precision=1)
            )
        with self.add_children_as_readables(StandardReadableFormat.CONFIG_SIGNAL):
            self.wavelength = soft_signal_rw(int, 488, units="nm")
        super().__init__(name=name)


class Led(StandardReadable):
    """A light that only switches on and off."""

    def __init__(self, name: str = "") -> None:
        with self.add_children_as_readables():
            self.enabled = soft_signal_rw(bool, True)
        super().__init__(name=name)


class Plans:
    """The plans the example offers."""

    def __init__(self, name: str) -> None:
        self.name = name

    def plan_map(self) -> Mapping[str, PlanEntry]:
        """Return the plans by name."""
        return {"walk": {"plan": self.walk}}

    def walk(
        self, motor: Axis, steps: int = 3, size: float = 1.0
    ) -> MsgGenerator[None]:
        """Send *motor* to *size*, then to twice *size*, and so on *steps* times, pausing after each move.

        The motor stays locked while the plan runs.
        """
        yield from lock_wrapper(strides(motor, steps, size), motor)


def strides(motor: Axis, steps: int, size: float) -> MsgGenerator[None]:
    """Yield the moves of a walk, and the pause after each."""
    for step in range(1, steps + 1):
        yield from bps.mv(motor, step * size)
        yield from bps.sleep(PAUSE)
