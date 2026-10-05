"""A presenter moving the axes of devices by hand."""

from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import math
from dataclasses import KW_ONLY, dataclass, field
from functools import partial
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from bluesky.protocols import Checkable, Stoppable
from bluesky.utils import maybe_await
from ophyd_async.core import (
    AsyncConfigurable,
    AsyncReadable,
    AsyncStatus,
    Device,
    SignalR,
    WatchableAsyncStatus,
    walk_devices,
)
from psygnal import Signal

from redsun.aio import cancel_task, run_coro
from redsun.log import Loggable
from redsun.ports import slot
from redsun.registry import DeviceMapping  # noqa: TC001
from redsun.utils.devices import (
    AxisInfo,
    Configuration,
    describe_axis,
    find_axes,
    limits,
    read_configuration,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping

    from bluesky.protocols import Reading

    from redsun.utils.devices import Axis


def label(device: str, axis: str) -> str:
    """Return how messages name *axis* of *device*: once when they are one."""
    return device if axis == device else f"{device} {axis}"


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
    The limits of an axis are read again after each configuration write to
    its device and after a move that is refused or fails, and before each move
    of an axis that is not `Checkable`; a change is reported on `sig_limits`.
    """

    sig_readback = Signal(str, str, float)
    """Device, axis and position, whenever the axis reads back."""

    sig_moving = Signal(str, bool)
    """Device, and whether it starts or ends a move."""

    sig_failed = Signal(str, str)
    """Device, and why a move or a stop failed."""

    sig_configuration = Signal(str, object)
    """Key and value of a configuration signal, whenever it changes and after a write."""

    sig_limits = Signal(str, str, object, object)
    """Device, axis, and its new low and high limits; `None` for no bound."""

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
        self._unsubscribers: list[Callable[[], None]] = []
        self._held: frozenset[str] = frozenset()
        self._from_setpoint: set[str] = set()
        self._moves: dict[str, asyncio.Task[None]] = {}
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
        the axis last reported, is refused. A subclass refusing more calls
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

        async def targets() -> dict[str, float]:
            location = await self._axes[device][axis].locate()
            start = (
                location["setpoint"]
                if device in self._from_setpoint
                else location["readback"]
            )
            return {axis: start + delta}

        await self._run(device, targets)

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

        async def targets() -> Mapping[str, float]:
            return positions

        await self._run(device, targets)

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
        targets: list[Stoppable] = [
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
        # a stop that reaches a device before its move has started cancels
        # nothing there, so the move it was asked for is cancelled as well
        move = self._moves.get(device)
        if move is not None:
            cancel_task(move)
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
    async def configure(self, key: str, value: object) -> None:
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
        device = self._owners[key]
        for axis in self._axes[device]:
            try:
                await self._read_limits(device, axis)
            except Exception:
                self.logger.exception(
                    f"Reading the limits of {label(device, axis)} failed"
                )

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
        self, device: str, targets: Callable[[], Awaitable[Mapping[str, float]]]
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
            failed = False
            try:
                for axis, target in (await targets()).items():
                    if self._stops[device] != stops:
                        break
                    await self._set(device, axis, target)
            except Exception as error:
                failed = True
                if self._stops[device] == stops:
                    self.logger.exception(f"Moving {device} failed")
                    self.sig_failed.emit(device, str(error) or type(error).__name__)
            finally:
                self.sig_moving.emit(device, False)
            stopped = self._stops[device] != stops
            if stopped:
                self.logger.info(f"Stopped {device}")
            if failed or stopped:
                self._from_setpoint.discard(device)
            else:
                self._from_setpoint.add(device)

    async def _set(self, device: str, axis: str, target: float) -> None:
        item = self._axes[device][axis]
        # an axis that checks its own targets reads its limits as it moves,
        # so reading them here would cost every step a round trip
        if not isinstance(item, Checkable):
            await self._read_limits(device, axis)
        try:
            self.check(device, axis, target)
            self.logger.info(f"Moving {label(device, axis)} to {target}")
            status = item.set(target)
            if not isinstance(status, AsyncStatus | WatchableAsyncStatus):
                raise TypeError(
                    f"{label(device, axis)}: set returned "
                    f"{type(status).__name__}, not an ophyd-async status"
                )
            self._moves[device] = status.task
            try:
                # waiting on the task rather than awaiting it lets a stop cancel
                # the move alone; leaving the block early cancels the move
                async with status:
                    await asyncio.wait({status.task})
            finally:
                del self._moves[device]
            if status.task.cancelled():
                raise RuntimeError(f"{label(device, axis)} was cancelled")
            if (error := status.exception()) is not None:
                raise error
        except Exception:
            # limits changed since they were read may be why, and the next
            # check and the view should have the new ones
            with contextlib.suppress(Exception):
                await self._read_limits(device, axis)
            raise

    async def _read_limits(self, device: str, axis: str) -> None:
        item = self._axes[device][axis]
        info = self._info[device][axis]
        if info.key is None or not isinstance(item, AsyncReadable):
            return
        described = await item.describe()
        new = limits(described.get(info.key, {}))
        if new != info.limits:
            self._info[device][axis] = dataclasses.replace(info, limits=new)
            self.sig_limits.emit(device, axis, *new)

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
            if configuration is not None:
                axis_info = dataclasses.replace(
                    axis_info, configuration=tuple(configuration.descriptors)
                )
                self._configuration.descriptors.update(configuration.descriptors)
                self._configuration.readings.update(configuration.readings)
                self._configuration.writable.update(configuration.writable)
                self._owners.update(dict.fromkeys(configuration.descriptors, device))
            info.setdefault(device, {})[name] = axis_info
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
        unsubscribers: list[Callable[[], None]] = []
        try:
            async with asyncio.timeout(self.timeout):
                info = await describe_axis(axis)
                relay = partial(self._relay, device, name, info.key)
                unsubscribers.append(partial(axis.clear_sub, relay))
                axis.subscribe(relay)
                configuration = (
                    await read_configuration(axis)
                    if isinstance(axis, AsyncConfigurable)
                    else None
                )
                children = (
                    walk_devices(axis).values() if isinstance(axis, Device) else ()
                )
                for signal in children:
                    if (
                        configuration is not None
                        and isinstance(signal, SignalR)
                        and signal.name in configuration.readings
                    ):
                        unsubscribers.append(
                            partial(signal.clear_sub, self._relay_configuration)
                        )
                        signal.subscribe_reading(self._relay_configuration)
        except Exception as error:  # noqa: BLE001
            self.logger.warning(f"Leaving out {label(device, name)}: {error!r}")
            for unsubscribe in unsubscribers:
                unsubscribe()
            return None, None
        self._unsubscribers.extend(unsubscribers)
        return info, configuration

    async def _unfollow(self) -> None:
        for unsubscribe in self._unsubscribers:
            unsubscribe()
        self._unsubscribers.clear()

    def _relay(
        self,
        device: str,
        axis: str,
        key: str | None,
        reading: dict[str, Reading[float]],
    ) -> None:
        # a callback that raises would reach whatever set the device's signal
        try:
            entry = reading.get(key) if key is not None else None
            value = (entry or next(iter(reading.values())))["value"]
            self.sig_readback.emit(device, axis, float(value))
        except Exception:
            self.logger.exception(
                f"Relaying a readback of {label(device, axis)} failed"
            )

    def _relay_configuration(self, reading: dict[str, Reading[object]]) -> None:
        try:
            for key, entry in reading.items():
                self.sig_configuration.emit(key, entry["value"])
        except Exception:
            self.logger.exception("Relaying a configuration value failed")
