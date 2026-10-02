"""A presenter moving the axes of devices by hand."""

from __future__ import annotations

import asyncio
import inspect
from functools import partial
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from bluesky.protocols import Stoppable
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
    from event_model import DataKey
    from ophyd_async.core import SignalRW

    from redsun.utils.devices import Axis


@runtime_checkable
class DescribesAxes(Protocol):
    """A component describing the axes it moves."""

    def axes(self) -> dict[str, dict[str, AxisInfo]]:
        """Return the axes of each device, by axis name, by device name."""
        ...

    def configuration(self) -> tuple[dict[str, DataKey], dict[str, Reading[Any]]]:
        """Return the configuration descriptors and readings of every axis."""
        ...


class PositionerPresenter(Loggable):
    """Move the axes of devices by hand, one move at a time per device.

    Every device with at least one axis is kept, or only those named in
    *include*. Each axis is followed from the start, and its readbacks are
    relayed on `sig_readback`.

    Parameters
    ----------
    include
        Names of the devices to keep; `None` keeps every device with an axis.
    """

    sig_readback = Signal(str, str, float)
    """Device, axis and position, whenever the axis reads back."""

    sig_moving = Signal(str, bool)
    """Device, and whether it starts or ends a move."""

    sig_failed = Signal(str, str)
    """Device, and the message of the move that raised."""

    sig_configuration = Signal(str, object)
    """Key and value of a configuration signal, read back after a write."""

    def __init__(
        self,
        name: str,
        *,
        devices: DeviceMapping,
        include: list[str] | None = None,
    ) -> None:
        self.name = name
        self._axes = {
            device: axes
            for device, item in devices.items()
            if (include is None or device in include) and (axes := find_axes(item))
        }
        self._writable: dict[str, SignalRW[Any]] = {}
        self._configuration: tuple[dict[str, DataKey], dict[str, Reading[Any]]] = (
            {},
            {},
        )
        self._callbacks: list[
            tuple[Axis, Callable[[dict[str, Reading[Any]]], None]]
        ] = []
        self._info = run_coro(self._follow())
        self._locks = {device: asyncio.Lock() for device in self._axes}
        self._stops = dict.fromkeys(self._axes, 0)

    def axes(self) -> dict[str, dict[str, AxisInfo]]:
        """Return the axes of each device, by axis name, by device name."""
        return self._info

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

        await self._run(device, self._stops[device], self._step, axis, delta)

    @slot
    async def move_to(self, device: str, positions: Mapping[str, float]) -> None:
        """Move the axes of *device* in *positions* there, one after another.

        Waits for a move of *device* already running, and is dropped if
        *device* is stopped meanwhile.

        Raises
        ------
        KeyError
            If the presenter does not hold *device*.
        """
        await self._run(device, self._stops[device], self._go, positions)

    @slot
    async def stop(self, device: str) -> None:
        """Stop every stoppable axis of *device*, ending a move it is making.

        Does not wait for the move, and a move ended this way is not reported
        as failed. A go-to waiting for *device* is dropped.

        Raises
        ------
        KeyError
            If the presenter does not hold *device*.
        """
        axes = [
            axis for axis in self._axes[device].values() if isinstance(axis, Stoppable)
        ]
        self._stops[device] += 1
        self.logger.info(f"Stopping {device}")
        for axis in axes:
            result = axis.stop(success=False)
            if inspect.isawaitable(result):
                await result

    def configuration(self) -> tuple[dict[str, DataKey], dict[str, Reading[Any]]]:
        """Return the configuration descriptors and readings of every axis.

        An entry whose signal cannot be written has `:readonly` appended to
        its source.
        """
        return self._configuration

    @slot
    async def configure(self, key: str, value: Any) -> None:
        """Write *value* to the configuration signal *key*, then report it.

        `sig_configuration` carries what the signal reads back, also after a
        write it refused, which is logged.

        Raises
        ------
        KeyError
            If *key* names no writable configuration signal.
        """
        signal = self._writable[key]
        try:
            await signal.set(value)
        except Exception:
            self.logger.exception(f"Setting {key} to {value!r} failed")
        self.sig_configuration.emit(key, await signal.get_value())

    def shutdown(self) -> None:
        """Stop following the axes."""
        run_coro(self._unfollow())

    async def _run(
        self,
        device: str,
        stops: int,
        motion: Callable[..., Awaitable[None]],
        *args: Any,
    ) -> None:
        async with self._locks[device]:
            if self._stops[device] != stops:
                self.logger.info(f"Not moving {device}: stopped while waiting")
                return
            self.sig_moving.emit(device, True)
            try:
                await motion(device, *args)
            except BaseException as error:
                # a stopped move ends with the device's error, or a cancelled
                # status; either way it ended as asked, not as a failure
                if self._stops[device] != stops:
                    self.logger.info(f"Stopped {device}")
                elif isinstance(error, Exception):
                    self.logger.exception(f"Moving {device} failed")
                    self.sig_failed.emit(device, str(error))
                else:
                    raise
            finally:
                self.sig_moving.emit(device, False)

    async def _step(self, device: str, axis: str, delta: float) -> None:
        movable = self._axes[device][axis]
        self.logger.info(f"Moving {device} {axis} by {delta}")
        await movable.set((await movable.locate())["readback"] + delta)

    async def _go(self, device: str, positions: Mapping[str, float]) -> None:
        for axis, position in positions.items():
            self.logger.info(f"Moving {device} {axis} to {position}")
            await self._axes[device][axis].set(position)

    async def _follow(self) -> dict[str, dict[str, AxisInfo]]:
        found = [
            (device, name, axis)
            for device, axes in self._axes.items()
            for name, axis in axes.items()
        ]
        followed = await asyncio.gather(*(self._follow_axis(*item) for item in found))
        info: dict[str, dict[str, AxisInfo]] = {}
        descriptors, readings = self._configuration
        for (device, name, _), (axis_info, configuration) in zip(
            found, followed, strict=True
        ):
            if axis_info is None:
                del self._axes[device][name]
                continue
            info.setdefault(device, {})[name] = axis_info
            if configuration is not None:
                descriptors.update(configuration.descriptors)
                readings.update(configuration.readings)
                self._writable.update(configuration.writable)
        self._axes = {device: axes for device, axes in self._axes.items() if axes}
        return info

    async def _follow_axis(
        self, device: str, name: str, axis: Axis
    ) -> tuple[AxisInfo | None, Configuration | None]:
        try:
            info = await describe_axis(axis)
        except Exception as error:  # noqa: BLE001
            self.logger.warning(f"Leaving out {device} {name}: {error}")
            return None, None
        callback = partial(self._relay, device, name)
        axis.subscribe(callback)
        self._callbacks.append((axis, callback))
        if not isinstance(axis, AsyncConfigurable):
            return info, None
        return info, await read_configuration(axis)

    async def _unfollow(self) -> None:
        for axis, callback in self._callbacks:
            axis.clear_sub(callback)
        self._callbacks.clear()

    def _relay(self, device: str, axis: str, reading: dict[str, Reading[Any]]) -> None:
        value = next(iter(reading.values()))["value"]
        self.sig_readback.emit(device, axis, float(value))
