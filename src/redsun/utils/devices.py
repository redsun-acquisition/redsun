"""What a device offers to be moved and set: its axes, limits and configuration.

These read an `ophyd-async` device through the protocols it implements, never
through attribute names, so they apply to any device.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass, field
from numbers import Real
from typing import TYPE_CHECKING, Any, Protocol, TypeGuard, runtime_checkable

from bluesky.protocols import HasHints, Stoppable, Subscribable
from ophyd_async.core import (
    AsyncLocatable,
    AsyncReadable,
    Device,
    Signal,
    SignalRW,
    StandardMovable,
    walk_rw_signals,
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from bluesky.protocols import Reading
    from event_model import DataKey
    from ophyd_async.core import AsyncConfigurable

__all__ = [
    "Axis",
    "AxisInfo",
    "Configuration",
    "DimmableLight",
    "Light",
    "LightInfo",
    "describe_axis",
    "describe_light",
    "dimmable",
    "find_axes",
    "is_light",
    "limits",
    "read_configuration",
    "walk_axes",
]


@runtime_checkable
class Axis(AsyncLocatable[float], Subscribable[float], Protocol):
    """Something `set` moves, `locate` reports and `subscribe` follows.

    `set` returns an `ophyd-async` status, which the positioner waits on and
    cancels to stop the move. Checking an object against this protocol at run
    time finds the methods only, not what `set` returns.
    """


@dataclass(frozen=True, slots=True)
class AxisInfo:
    """What a view shows of an axis before its first readback arrives."""

    position: float
    """Readback when the axis was described."""

    units: str | None
    """Engineering units of the axis, from its descriptor."""

    precision: int | None
    """Decimals the descriptor asks for."""

    limits: tuple[float | None, float | None] = (None, None)
    """Lowest and highest position the descriptor allows; `None` for no bound."""

    stoppable: bool = False
    """Whether the axis can be stopped, by itself or through its device."""

    key: str | None = None
    """Data key of the readback in the readings the axis reports."""

    configuration: tuple[str, ...] = ()
    """Keys of the axis' configuration entries."""


@dataclass(slots=True)
class Configuration:
    """A device's configuration, and which of its signals can be written."""

    descriptors: dict[str, DataKey]
    """Descriptors by key; a read-only entry has `:readonly` appended to its source."""

    readings: dict[str, Reading[Any]]
    """Readings by key."""

    writable: dict[str, SignalRW[Any]]
    """The writable signals among them, by key."""

    owners: dict[str, str] = field(default_factory=dict)
    """Name of the device each key belongs to; empty when not known."""


def is_axis(item: object) -> TypeGuard[Axis]:
    """Tell whether *item* is an axis: one that is not a signal."""
    return isinstance(item, Axis) and not isinstance(item, Signal)


def walk_axes(device: Device, path_prefix: str = "") -> Iterator[tuple[str, Axis]]:
    """Yield the axes under *device* with their dotted attribute paths.

    The walk stops at each axis it finds, so the signals of an axis are never
    yielded, and it does not enter signals.

    Parameters
    ----------
    path_prefix
        Prefix of the yielded paths; left blank by a caller.
    """
    for name, child in device.children():
        path = f"{path_prefix}{name}"
        if is_axis(child):
            yield path, child
        elif not isinstance(child, Signal):
            yield from walk_axes(child, f"{path}.")


def find_axes(device: Device) -> dict[str, Axis]:
    """Return the axes of *device*, by name.

    A device that is itself an axis is its only axis, under its own name.
    Otherwise each axis under it is keyed by its attribute name, or by its
    dotted path when another axis of the device shares that name. A signal
    is never an axis, though a writable one can be set and located.
    """
    if is_axis(device):
        return {device.name: device}
    found = {path: (path.rpartition(".")[2], axis) for path, axis in walk_axes(device)}
    shared = Counter(name for name, _ in found.values())
    return {
        path if shared[name] > 1 else name: axis for path, (name, axis) in found.items()
    }


def limits(descriptor: Mapping[str, Any]) -> tuple[float | None, float | None]:
    """Return the lowest and highest value *descriptor* allows; `None` for no bound.

    Control limits come first, display limits otherwise. A pair whose low is
    not below its high counts as no limits: EPICS reports `0` and `0` for a
    record that has none.
    """
    bounds = descriptor.get("limits") or {}
    bounds = bounds.get("control") or bounds.get("display") or {}
    low, high = bounds.get("low"), bounds.get("high")
    if low is not None and high is not None and low >= high:
        return None, None
    return low, high


async def describe_axis(axis: Axis) -> AxisInfo:
    """Return where *axis* stands and what its readback descriptor says.

    The descriptor is the entry of the readback a `StandardMovable` names,
    otherwise of the axis' first hint, or its only entry; an axis that is not
    readable has none. Units that are not text, and a
    precision that is not a whole number of at least 0, are left out.

    Raises
    ------
    TypeError
        If the position of *axis* is not a number.
    """
    if isinstance(axis, AsyncReadable):
        location, described = await asyncio.gather(axis.locate(), axis.describe())
    else:
        location, described = await axis.locate(), {}
    # typed as a float, but a device may report anything
    position: object = location["readback"]
    if isinstance(position, bool) or not isinstance(position, Real):
        raise TypeError(f"its position {position!r} is not a number")
    hinted = axis.hints.get("fields", []) if isinstance(axis, HasHints) else []
    if isinstance(axis, StandardMovable):
        key: str | None = axis.movable_logic.readback.name
    elif hinted:
        key = hinted[0]
    elif len(described) == 1:
        key = next(iter(described))
    else:
        key = None
    descriptor: Mapping[str, Any] = described.get(key, {}) if key is not None else {}
    units = descriptor.get("units")
    precision = descriptor.get("precision")
    return AxisInfo(
        position=float(position),
        units=units if isinstance(units, str) else None,
        precision=precision
        if isinstance(precision, int)
        and not isinstance(precision, bool)
        and precision >= 0
        else None,
        limits=limits(descriptor),
        stoppable=isinstance(axis, Stoppable),
        key=key,
    )


async def read_configuration(device: AsyncConfigurable) -> Configuration:
    """Read the configuration of *device*, marking what cannot be written."""
    descriptors, readings = await asyncio.gather(
        device.describe_configuration(), device.read_configuration()
    )
    signals = walk_rw_signals(device).values() if isinstance(device, Device) else ()
    writable = {signal.name: signal for signal in signals if signal.name in readings}
    marked: dict[str, DataKey] = {
        key: descriptor
        if key in writable
        else descriptor | {"source": f"{descriptor['source']}:readonly"}
        for key, descriptor in descriptors.items()
    }
    return Configuration(
        descriptors=marked,
        readings=dict(readings),
        writable=writable,
    )


@runtime_checkable
class Light(Protocol):
    """A light source that can be switched on and off."""

    @property
    def enabled(self) -> SignalRW[bool]:
        """On when `True`."""
        ...


@runtime_checkable
class DimmableLight(Light, Protocol):
    """A light whose intensity can also be set."""

    @property
    def intensity(self) -> SignalRW[float]:
        """How bright the light is, in the units its descriptor gives."""
        ...


@dataclass(frozen=True, slots=True)
class LightInfo:
    """What a view shows of a light before its first readback arrives."""

    enabled: bool
    """Whether the light was on when described."""

    intensity: float | None = None
    """Intensity when described; `None` for a light that has none."""

    units: str | None = None
    """Units of the intensity, from its descriptor."""

    precision: int | None = None
    """Decimals the intensity's descriptor asks for."""

    limits: tuple[float | None, float | None] = (None, None)
    """Lowest and highest intensity the descriptor allows; `None` for no bound."""


def is_light(item: object) -> TypeGuard[Light]:
    """Tell whether *item* is a light: its `enabled` is a boolean signal it can write.

    A device whose `intensity` is not a numeric signal it can write counts as
    a light without intensity.
    """
    enabled = getattr(item, "enabled", None)
    return isinstance(enabled, SignalRW) and enabled.datatype is bool


def dimmable(light: Light) -> TypeGuard[DimmableLight]:
    """Tell whether *light* has an intensity that is a numeric signal it can write."""
    intensity = getattr(light, "intensity", None)
    return isinstance(intensity, SignalRW) and intensity.datatype in (int, float)


async def describe_light(light: Light) -> LightInfo:
    """Return the state of *light* and what its intensity's descriptor says."""
    enabled = await light.enabled.get_value()
    if not dimmable(light):
        return LightInfo(enabled=bool(enabled))
    whole = light.intensity.datatype is int
    value, described = await asyncio.gather(
        light.intensity.get_value(), light.intensity.describe()
    )
    descriptor: Mapping[str, Any] = described.get(light.intensity.name, {})
    units = descriptor.get("units")
    precision = descriptor.get("precision")
    return LightInfo(
        enabled=bool(enabled),
        intensity=float(value),
        units=units if isinstance(units, str) else None,
        precision=0
        if whole
        else precision
        if isinstance(precision, int)
        and not isinstance(precision, bool)
        and precision >= 0
        else None,
        limits=limits(descriptor),
    )
