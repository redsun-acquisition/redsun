"""A presenter moving the axes of devices by hand."""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from bluesky.protocols import HasHints, Stoppable
from ophyd_async.core import AsyncConfigurable, AsyncReadable, Device, SignalRW
from psygnal import Signal

from redsun.aio import run_coro
from redsun.log import Loggable
from redsun.ports import slot
from redsun.registry import DeviceMapping  # noqa: TC001

from ._axes import find_axes

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping

    from bluesky.protocols import Reading
    from event_model import DataKey

    from ._axes import Axis


@dataclass(frozen=True, slots=True)
class AxisInfo:
    """What a view shows of an axis before its first readback arrives."""

    position: float
    """Readback when the presenter started."""

    units: str | None
    """Engineering units of the axis, from its descriptor."""

    precision: int | None
    """Decimals the descriptor asks for."""

    limits: tuple[float | None, float | None] = (None, None)
    """Lowest and highest position the descriptor allows; `None` for no bound."""

    stoppable: bool = False
    """Whether the axis can be stopped."""


def writable_signals(device: Device) -> dict[str, SignalRW[Any]]:
    """Return every writable signal under *device*, by signal name."""
    found: dict[str, SignalRW[Any]] = {}
    for _, child in device.children():
        if isinstance(child, SignalRW):
            found[child.name] = child
        else:
            found.update(writable_signals(child))
    return found


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

        async def step() -> None:
            movable = self._axes[device][axis]
            self.logger.info(f"Moving {device} {axis} by {delta}")
            await movable.set((await movable.locate())["readback"] + delta)

        await self._run(device, self._stops[device], step)

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

        async def go() -> None:
            for axis, position in positions.items():
                self.logger.info(f"Moving {device} {axis} to {position}")
                await self._axes[device][axis].set(position)

        await self._run(device, self._stops[device], go)

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
        self, device: str, stops: int, motion: Callable[[], Awaitable[None]]
    ) -> None:
        async with self._locks[device]:
            if self._stops[device] != stops:
                self.logger.info(f"Not moving {device}: stopped while waiting")
                return
            self.sig_moving.emit(device, True)
            try:
                await motion()
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

    async def _follow(self) -> dict[str, dict[str, AxisInfo]]:
        info: dict[str, dict[str, AxisInfo]] = {}
        descriptors, readings = self._configuration
        for device, axes in list(self._axes.items()):
            info[device] = {}
            for name, axis in list(axes.items()):
                try:
                    info[device][name] = await self._describe(axis)
                except Exception as error:  # noqa: BLE001
                    self.logger.warning(f"Leaving out {device} {name}: {error}")
                    del axes[name]
                    continue
                callback = partial(self._relay, device, name)
                axis.subscribe(callback)
                self._callbacks.append((axis, callback))
                if not isinstance(axis, AsyncConfigurable):
                    continue
                writable = writable_signals(axis) if isinstance(axis, Device) else {}
                for key, descriptor in (await axis.describe_configuration()).items():
                    if key in writable:
                        self._writable[key] = writable[key]
                        descriptors[key] = descriptor
                    else:
                        descriptors[key] = {
                            **descriptor,
                            "source": f"{descriptor['source']}:readonly",
                        }
                readings.update(await axis.read_configuration())
            if not axes:
                del self._axes[device]
                del info[device]
        return info

    async def _unfollow(self) -> None:
        for axis, callback in self._callbacks:
            axis.clear_sub(callback)
        self._callbacks.clear()

    @staticmethod
    async def _describe(axis: Axis) -> AxisInfo:
        position = (await axis.locate())["readback"]
        if isinstance(position, bool) or not isinstance(position, (int, float)):
            raise TypeError(f"its position {position!r} is not a number")
        descriptor: dict[str, Any] = {}
        if isinstance(axis, AsyncReadable):
            described = await axis.describe()
            fields = axis.hints.get("fields", []) if isinstance(axis, HasHints) else []
            key = (
                fields[0]
                if fields
                else next(iter(described))
                if len(described) == 1
                else None
            )
            descriptor = dict(described.get(key, {})) if key is not None else {}
        bounds = descriptor.get("limits", {})
        bounds = bounds.get("control") or bounds.get("display") or {}
        low, high = bounds.get("low"), bounds.get("high")
        # EPICS reports limits of 0 and 0 for an axis that has none
        if low is not None and high is not None and low >= high:
            low = high = None
        return AxisInfo(
            position=float(position),
            units=descriptor.get("units"),
            precision=descriptor.get("precision"),
            limits=(low, high),
            stoppable=isinstance(axis, Stoppable),
        )

    def _relay(self, device: str, axis: str, reading: dict[str, Reading[Any]]) -> None:
        value = next(iter(reading.values()))["value"]
        self.sig_readback.emit(device, axis, float(value))
