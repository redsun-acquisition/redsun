"""Mock classes for redsun SDK tests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np
from ophyd_async.core import (
    AsyncStatus,
    Device,
    DeviceMap,
    MovableLogic,
    SignalR,
    SignalRW,
    SoftSignalBackend,
    StandardMovable,
    StandardReadable,
    StandardReadableFormat,
    soft_signal_r_and_setter,
    soft_signal_rw,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from bluesky.protocols import Location, Reading
    from event_model import DataKey
    from ophyd_async.core import TimeoutCalculator


class MockDetector(StandardReadable):
    """Mock detector device using soft signals.

    The EGU for `exposure` is embedded in the descriptor document
    (`describe()["<name>-exposure"]["units"]`), not as a separate signal.
    """

    exposure: SignalRW[float]
    integer: SignalRW[int]
    floating: SignalRW[float]

    def __init__(self, name: str) -> None:
        with self.add_children_as_readables():
            self.exposure = soft_signal_rw(float, initial_value=1.0, units="ms")
            self.integer = soft_signal_rw(int, initial_value=0)
            self.floating = soft_signal_rw(float, initial_value=0.0)
        super().__init__(name=name)


class RoiDetector(StandardReadable):
    """A detector with a settable region of interest and a fixed sensor shape."""

    roi: SignalRW[np.ndarray]
    sensor_shape: SignalR[np.ndarray]

    def __init__(self, name: str) -> None:
        with self.add_children_as_readables():
            self.roi = soft_signal_rw(
                np.ndarray, initial_value=np.array([0, 0, 512, 512], dtype=np.int32)
            )
            self.sensor_shape, _ = soft_signal_r_and_setter(
                np.ndarray, initial_value=np.array([512, 512], dtype=np.int32)
            )
        super().__init__(name=name)


class NumberSwitchDevice(StandardReadable):
    """A device whose `enabled` is a number, not a light switch."""

    def __init__(self, name: str = "") -> None:
        self.enabled = soft_signal_rw(int, 1)
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

    async def move(self, new_position: float, timeout: TimeoutCalculator) -> None:
        """Wait for `gate`, when it is set, then write the setpoint."""
        if self.gate is not None:
            await self.gate.wait()
        await self.setpoint.set(new_position)


@dataclass
class LimitedLogic(GatedLogic):
    """Move logic refusing targets more than 5 from `offset`, as a motor record does."""

    offset: SignalRW[float] | None = None

    async def check_move(self, new_position: float) -> None:
        """Refuse a target outside the limits the offset sets."""
        await super().check_move(new_position)
        offset = 0.0 if self.offset is None else await self.offset.get_value()
        if abs(new_position - offset) > 5.0:
            raise ValueError(f"{new_position} is outside the limits")


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
    """A soft axis with limits of -5 and 5, shifted by its writable `offset`."""

    def __init__(self, name: str = "") -> None:
        with self.add_children_as_readables(StandardReadableFormat.CONFIG_SIGNAL):
            self.offset = soft_signal_rw(float, 0.0, units="um")
        super().__init__(name)
        self.logic = LimitedLogic(
            setpoint=self.position, readback=self.position, offset=self.offset
        )

    async def describe(self) -> dict[str, DataKey]:
        """Describe the axis, with its limits on every entry."""
        described = await super().describe()
        offset = await self.offset.get_value()
        for descriptor in described.values():
            descriptor["limits"] = {
                "control": {"low": offset - 5.0, "high": offset + 5.0}
            }
        return described


class Stage(StandardReadable):
    """A device holding its axes in a `DeviceMap`, plus a plain signal."""

    def __init__(self, name: str, axes: tuple[str, ...] = ("x", "theta")) -> None:
        self.axis = DeviceMap({axis: SoftAxis() for axis in axes})
        self.add_readables(list(self.axis.values()))
        with self.add_children_as_readables(StandardReadableFormat.CONFIG_SIGNAL):
            self.speed = soft_signal_rw(float, 1.0)
        super().__init__(name=name)


class XYStage(StandardReadable):
    """A device with the soft axes `x` and `y` as attributes."""

    x: SoftAxis
    y: SoftAxis

    def __init__(self, name: str, /) -> None:
        self.x = SoftAxis()
        self.y = SoftAxis()
        super().__init__(name=name)


class TwinStage(StandardReadable):
    """A device with two groups whose axes share the name `x`."""

    def __init__(self, name: str) -> None:
        self.left = DeviceMap({"x": SoftAxis()})
        self.right = DeviceMap({"x": SoftAxis()})
        super().__init__(name=name)


@dataclass
class LaggingLogic(MovableLogic[float]):
    """Move logic whose readback lands `lag` short of the setpoint."""

    set_readback: Callable[[float], None] | None = None
    lag: float = 0.004

    async def move(self, new_position: float, timeout: TimeoutCalculator) -> None:
        """Write the setpoint, then a readback `lag` short of it."""
        await self.setpoint.set(new_position)
        if self.set_readback is not None:
            self.set_readback(new_position - self.lag)


class LaggingAxis(StandardReadable, StandardMovable[float]):
    """An axis whose readback stops short of its setpoint, as in a deadband."""

    def __init__(self, name: str = "") -> None:
        with self.add_children_as_readables(StandardReadableFormat.HINTED_SIGNAL):
            self.readback, set_readback = soft_signal_r_and_setter(float, 0.0)
        self.setpoint = soft_signal_rw(float, 0.0)
        self.logic = LaggingLogic(
            setpoint=self.setpoint, readback=self.readback, set_readback=set_readback
        )
        super().__init__(name=name)

    @property
    def movable_logic(self) -> MovableLogic[float]:
        """Separate setpoint and readback."""
        return self.logic


class QuietAxis(Device):
    """An axis whose move ends without an error when it is stopped."""

    def __init__(self, name: str = "") -> None:
        self.position = soft_signal_rw(float, 0.0)
        self.gate = asyncio.Event()
        self.started = False
        self.stopped = False
        super().__init__(name=name)

    @AsyncStatus.wrap
    async def set(self, value: float) -> None:
        """Wait for the gate, then move unless stopped meanwhile."""
        self.started = True
        await self.gate.wait()
        if not self.stopped:
            await self.position.set(value)

    async def locate(self) -> Location[float]:
        """Return the position as setpoint and readback."""
        value = await self.position.get_value()
        return {"setpoint": value, "readback": value}

    def subscribe(self, function: Callable[[dict[str, Reading[float]]], None]) -> None:
        """Follow the position."""
        self.position.subscribe_reading(function)

    def clear_sub(self, function: Callable[[dict[str, Reading[float]]], None]) -> None:
        """Stop following the position."""
        self.position.clear_sub(function)

    async def stop(self, success: bool = False) -> None:
        """End the move in progress quietly."""
        self.stopped = True
        self.gate.set()


class QuietStage(Device):
    """A device with two axes whose moves end quietly when stopped."""

    def __init__(self, name: str) -> None:
        self.a = QuietAxis()
        self.b = QuietAxis()
        super().__init__(name=name)


class StuckStopAxis(SoftAxis):
    """A soft axis whose stop command fails."""

    async def stop(self, success: bool = False) -> None:
        """Fail as a stop write that times out."""
        raise ConnectionError("stop write timed out")


class StuckStage(StandardReadable):
    """A device whose axis `x` stops and whose axis `theta` fails to."""

    def __init__(self, name: str) -> None:
        self.axis = DeviceMap({"x": SoftAxis(), "theta": StuckStopAxis()})
        super().__init__(name=name)


class BrokenConfigAxis(SoftAxis):
    """A soft axis whose configuration cannot be read."""

    async def read_configuration(self) -> dict[str, Reading[Any]]:
        """Fail as a configuration read that times out."""
        raise TimeoutError("configuration read timed out")


class HangingAxis(SoftAxis):
    """A soft axis whose position is never reported."""

    async def locate(self) -> Location[float]:
        """Wait forever."""
        await asyncio.Event().wait()
        raise AssertionError("unreachable")


class PlainStatus:
    """A bluesky status that is not an ophyd-async one, finished or finished later."""

    def __init__(self, done: bool = True) -> None:
        self.done = done
        self.callbacks: list[Callable[[PlainStatus], None]] = []

    @property
    def success(self) -> bool:
        """Whether the status is finished, which is always well."""
        return self.done

    def add_callback(self, callback: Callable[[PlainStatus], None]) -> None:
        """Call *callback* at once when finished, else when `finish` is called."""
        if self.done:
            callback(self)
        else:
            self.callbacks.append(callback)

    def exception(self, timeout: float | None = 0.0) -> BaseException | None:
        """Report no error."""
        return None

    def finish(self) -> None:
        """Finish the status and call the callbacks added before."""
        self.done = True
        for callback in self.callbacks:
            callback(self)


class PlainStatusAxis(SoftAxis):
    """A soft axis whose `set` returns a status not made by ophyd-async."""

    def set(self, value: float, timeout: object = None) -> PlainStatus:  # type: ignore[override]
        """Return a finished status without moving."""
        return PlainStatus()


class BoundedBackend(SoftSignalBackend[float]):
    """A soft float backend whose descriptor reports control limits."""

    def __init__(self, low: float, high: float, value: float, units: str) -> None:
        super().__init__(float, value, units=units, precision=1)
        self.bounds = (low, high)

    async def get_datakey(self, source: str) -> DataKey:
        """Describe the signal, with its limits."""
        key = await super().get_datakey(source)
        key["limits"] = {"control": {"low": self.bounds[0], "high": self.bounds[1]}}
        return key


def bounded_signal(
    low: float, high: float, value: float, units: str
) -> SignalRW[float]:
    """Return a soft float signal limited to *low* and *high*."""
    return SignalRW(BoundedBackend(low, high, value, units))


class SoftLight(StandardReadable):
    """A light that is switched on and off, with its wavelength as configuration."""

    def __init__(self, name: str = "") -> None:
        with self.add_children_as_readables():
            self.enabled = soft_signal_rw(bool, False)
        with self.add_children_as_readables(StandardReadableFormat.CONFIG_SIGNAL):
            self.wavelength = soft_signal_rw(int, 650, units="nm")
        super().__init__(name=name)


class DimmerLight(SoftLight):
    """A soft light whose intensity is set from 0 to 100 mW."""

    def __init__(self, name: str = "") -> None:
        with self.add_children_as_readables():
            self.intensity = bounded_signal(0.0, 100.0, 10.0, "mW")
        super().__init__(name=name)


class WholeLight(SoftLight):
    """A soft light whose intensity is a whole number with no limits."""

    def __init__(self, name: str = "") -> None:
        with self.add_children_as_readables():
            self.intensity = soft_signal_rw(int, 5, units="%")
        super().__init__(name)
