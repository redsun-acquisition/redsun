"""A presenter moving the axes of devices by hand."""

from __future__ import annotations

import asyncio
import dataclasses
import math
from dataclasses import KW_ONLY, dataclass, field
from functools import partial
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from bluesky.protocols import Stoppable
from bluesky.utils import maybe_await
from ophyd_async.core import AsyncConfigurable
from psygnal import Signal

from redsun.aio import run_coro
from redsun.log import Loggable
from redsun.ports import slot
from redsun.registry import DeviceMapping  # noqa: TC001
from redsun.utils.devices import (
    AxisInfo,
    Configuration,
    describe_axis,
    find_axes,
    read_configuration,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping

    from bluesky.protocols import Reading

    from redsun.utils.devices import Axis


@runtime_checkable
class DescribesAxes(Protocol):
    """A component describing the axes it moves."""

    @property
    def axes(self) -> Mapping[str, Mapping[str, AxisInfo]]:
        """The axes of each device, by axis name, by device name."""
        ...

    @property
    def configuration(self) -> Configuration:
        """The configuration of every axis."""
        ...


@dataclass(eq=False)
class PositionerPresenter(Loggable):
    """Move the axes of devices by hand, one move at a time per device.

    Every device with at least one axis is kept, or only those named in
    `include`. Each axis is described and followed from the start, and its
    readbacks are relayed on `sig_readback`; an axis that cannot be, within
    `timeout`, is left out with a warning.

    A step starts from the setpoint, so steps add up exactly, and from the
    readback after a stop or a failure, when the setpoint no longer says
    where the axis is. Every target passes
    [`check`][redsun.presenter.PositionerPresenter.check] before it is sent.
    """

    sig_readback = Signal(str, str, float)
    """Device, axis and position, whenever the axis reads back."""

    sig_moving = Signal(str, bool)
    """Device, and whether it starts or ends a move."""

    sig_failed = Signal(str, str)
    """Device, and why a move or a stop failed."""

    sig_configuration = Signal(str, object)
    """Key and value of a configuration signal, read back after a write."""

    name: str
    """Name of the presenter in its session."""

    _: KW_ONLY

    devices: DeviceMapping = field(repr=False)
    """Devices of the session, searched for axes."""

    include: list[str] | None = None
    """Names of the devices to keep; `None` keeps every device with an axis."""

    timeout: float = 10.0
    """Seconds an axis may take to be described and followed at the start."""

    def __post_init__(self) -> None:
        unknown = sorted(set(self.include or ()) - set(self.devices))
        if unknown:
            self.logger.warning(f"No device named {', '.join(unknown)} to include")
        self._axes = {
            device: axes
            for device, item in self.devices.items()
            if (self.include is None or device in self.include)
            and (axes := find_axes(item))
        }
        self._configuration = Configuration(descriptors={}, readings={}, writable={})
        self._owners: dict[str, str] = {}
        self._callbacks: list[
            tuple[Axis, Callable[[dict[str, Reading[Any]]], None]]
        ] = []
        self._held: frozenset[str] = frozenset()
        self._from_setpoint: set[str] = set()
        try:
            self._info = run_coro(self._follow())
        except BaseException:
            run_coro(self._unfollow())
            raise
        self._locks = {device: asyncio.Lock() for device in self._axes}
        self._stops = dict.fromkeys(self._axes, 0)

    @property
    def axes(self) -> dict[str, dict[str, AxisInfo]]:
        """The axes of each device, by axis name, by device name."""
        return self._info

    @property
    def configuration(self) -> Configuration:
        """The configuration of every axis.

        An entry whose signal cannot be written has `:readonly` appended to
        its source.
        """
        return self._configuration

    def check(self, device: str, axis: str, target: float) -> None:
        """Refuse *target* for *axis* of *device*, or return.

        A target that is not a finite number, or that falls outside the limits
        the axis reports, is refused. A subclass refusing more calls
        `super().check` first.

        Raises
        ------
        ValueError
            With the reason, if the target is refused.
        """
        if not math.isfinite(target):
            raise ValueError(f"{axis} target {target} is not a finite number")
        low, high = self._info[device][axis].limits
        if (low is not None and target < low) or (high is not None and target > high):
            raise ValueError(f"{axis} target {target:g} is outside {low} to {high}")

    @slot
    async def move(self, device: str, axis: str, delta: float) -> None:
        """Move *axis* of *device* by *delta*, in the axis' units.

        Skipped while *device* is still moving, so steps asked faster than
        the device moves do not queue up behind it.

        Raises
        ------
        KeyError
            If the presenter does not hold *device*.
        """
        if self._locks[device].locked():
            self.logger.debug(f"Skipping a step of {device}, still moving")
            return
        await self._run(device, self._step, axis, delta)

    @slot
    async def move_to(self, device: str, positions: Mapping[str, float]) -> None:
        """Move the axes of *device* in *positions* there, one after another.

        Waits for a move of *device* already running, and is dropped if
        *device* is stopped, or taken by a plan, meanwhile.

        Raises
        ------
        KeyError
            If the presenter does not hold *device*.
        """
        await self._run(device, self._go, positions)

    @slot
    async def stop(self, device: str) -> None:
        """Stop *device* and each of its axes that can be stopped.

        Every one is asked at once, and one that fails does not keep the rest
        from stopping: the failures are reported on `sig_failed`. A move
        ended this way is not reported as failed, and a go-to waiting for
        *device* is dropped.

        Raises
        ------
        KeyError
            If the presenter does not hold *device*.
        """
        targets: list[Any] = [
            axis for axis in self._axes[device].values() if isinstance(axis, Stoppable)
        ]
        whole: object = self.devices.get(device)
        if isinstance(whole, Stoppable) and whole not in targets:
            targets.append(whole)
        if not targets:
            self.logger.warning(f"{device} has nothing that can be stopped")
            return
        self._stops[device] += 1
        self._from_setpoint.discard(device)
        self.logger.info(f"Stopping {device}")
        results = await asyncio.gather(
            *(maybe_await(target.stop(success=False)) for target in targets),
            return_exceptions=True,
        )
        failures = [result for result in results if isinstance(result, BaseException)]
        for failure in failures:
            self.logger.error(f"Stopping {device} failed: {failure!r}")
        if failures:
            self.sig_failed.emit(device, f"stopping failed: {failures[0]}")

    @slot
    def set_locked(self, names: frozenset[str]) -> None:
        """Hold the devices in *names* for a plan.

        No hand move, waiting go-to or configuration write reaches a held
        device.
        """
        self._held = names

    @slot
    async def configure(self, key: str, value: Any) -> None:
        """Write *value* to the configuration signal *key*, then report it.

        `sig_configuration` carries what the signal reads back, also after a
        write that was refused, or not made because a plan holds the device.

        Raises
        ------
        KeyError
            If *key* names no writable configuration signal.
        """
        signal = self._configuration.writable[key]
        if self._owners[key] in self._held:
            self.logger.warning(f"Not setting {key}: a plan holds its device")
        else:
            try:
                await signal.set(value)
            except Exception:
                self.logger.exception(f"Setting {key} to {value!r} failed")
        try:
            current = await signal.get_value()
        except Exception:
            self.logger.exception(f"Reading {key} back failed")
            return
        self.sig_configuration.emit(key, current)

    def shutdown(self) -> None:
        """Stop the devices still moving, then stop following the axes."""
        run_coro(self._shut_down(), timeout=self.timeout)

    async def _shut_down(self) -> None:
        moving = [device for device, lock in self._locks.items() if lock.locked()]
        await asyncio.gather(
            *(self.stop(device) for device in moving), return_exceptions=True
        )
        await self._unfollow()

    async def _run(
        self, device: str, motion: Callable[..., Awaitable[None]], *args: Any
    ) -> None:
        stops = self._stops[device]
        async with self._locks[device]:
            if self._stops[device] != stops:
                self.logger.info(f"Not moving {device}: stopped while waiting")
                return
            if device in self._held:
                self.logger.info(f"Not moving {device}: a plan holds it")
                return
            self.sig_moving.emit(device, True)
            try:
                await motion(device, stops, *args)
            except BaseException as error:
                task = asyncio.current_task()
                if task is not None and task.cancelling():
                    raise
                # a stopped move ends with the device's error, or a cancelled
                # status; either way it ended as asked, not as a failure
                self._from_setpoint.discard(device)
                if self._stops[device] != stops:
                    self.logger.info(f"Stopped {device}")
                elif isinstance(error, Exception):
                    self.logger.exception(f"Moving {device} failed")
                    self.sig_failed.emit(device, str(error) or type(error).__name__)
                else:
                    raise
            else:
                self._from_setpoint.add(device)
            finally:
                self.sig_moving.emit(device, False)

    async def _step(self, device: str, stops: int, axis: str, delta: float) -> None:
        location = await self._axes[device][axis].locate()
        start = (
            location["setpoint"]
            if device in self._from_setpoint
            else location["readback"]
        )
        await self._set(device, stops, axis, start + delta)

    async def _go(
        self, device: str, stops: int, positions: Mapping[str, float]
    ) -> None:
        for axis, position in positions.items():
            await self._set(device, stops, axis, position)

    async def _set(self, device: str, stops: int, axis: str, target: float) -> None:
        if self._stops[device] != stops:
            raise RuntimeError(f"{device} was stopped")
        self.check(device, axis, target)
        self.logger.info(f"Moving {device} {axis} to {target}")
        await self._axes[device][axis].set(target)

    async def _follow(self) -> dict[str, dict[str, AxisInfo]]:
        found = [
            (device, name, axis)
            for device, axes in self._axes.items()
            for name, axis in axes.items()
        ]
        followed = await asyncio.gather(*(self._follow_axis(*item) for item in found))
        info: dict[str, dict[str, AxisInfo]] = {}
        for (device, name, _), (axis_info, configuration) in zip(
            found, followed, strict=True
        ):
            if axis_info is None:
                del self._axes[device][name]
                continue
            info.setdefault(device, {})[name] = axis_info
            if configuration is not None:
                self._configuration.descriptors.update(configuration.descriptors)
                self._configuration.readings.update(configuration.readings)
                self._configuration.writable.update(configuration.writable)
                self._owners.update(dict.fromkeys(configuration.descriptors, device))
        self._axes = {device: axes for device, axes in self._axes.items() if axes}
        stoppable = {
            device
            for device in self._axes
            if isinstance(self.devices.get(device), Stoppable)
        }
        return {
            device: {
                name: dataclasses.replace(axis_info, stoppable=True)
                if device in stoppable
                else axis_info
                for name, axis_info in axes.items()
            }
            for device, axes in info.items()
        }

    async def _follow_axis(
        self, device: str, name: str, axis: Axis
    ) -> tuple[AxisInfo | None, Configuration | None]:
        subscribed: Callable[[dict[str, Reading[Any]]], None] | None = None
        try:
            async with asyncio.timeout(self.timeout):
                info = await describe_axis(axis)
                subscribed = partial(self._relay, device, name, info.key)
                self._callbacks.append((axis, subscribed))
                axis.subscribe(subscribed)
                configuration = (
                    await read_configuration(axis)
                    if isinstance(axis, AsyncConfigurable)
                    else None
                )
        except Exception as error:  # noqa: BLE001
            self.logger.warning(f"Leaving out {device} {name}: {error!r}")
            if subscribed is not None:
                self._callbacks.remove((axis, subscribed))
                axis.clear_sub(subscribed)
            return None, None
        return info, configuration

    async def _unfollow(self) -> None:
        for axis, callback in self._callbacks:
            axis.clear_sub(callback)
        self._callbacks.clear()

    def _relay(
        self, device: str, axis: str, key: str | None, reading: dict[str, Reading[Any]]
    ) -> None:
        # a callback that raises would reach whatever set the device's signal
        try:
            entry = reading.get(key) if key is not None else None
            value = (entry or next(iter(reading.values())))["value"]
            self.sig_readback.emit(device, axis, float(value))
        except Exception:
            self.logger.exception(f"Relaying a readback of {device} {axis} failed")
