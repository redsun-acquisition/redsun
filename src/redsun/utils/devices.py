"""What a device offers to be moved and set: its axes, limits and configuration.

These read an `ophyd-async` device through the protocols it implements, never
through attribute names, so they apply to any device.
"""

from __future__ import annotations

import asyncio
import dataclasses
from dataclasses import dataclass, field
from numbers import Real
from typing import (
    TYPE_CHECKING,
    Any,
    NamedTuple,
    Protocol,
    TypeGuard,
    runtime_checkable,
)

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
    from collections.abc import Mapping
    from collections.abc import Set as AbstractSet

    from bluesky.protocols import Reading
    from event_model import DataKey
    from ophyd_async.core import AsyncConfigurable, AsyncStatus, WatchableAsyncStatus

__all__ = [
    "Axis",
    "AxisInfo",
    "Configuration",
    "DevicePath",
    "DimmableLight",
    "Light",
    "LightInfo",
    "Readback",
    "describe_axis",
    "describe_light",
    "device_path",
    "dimmable",
    "held_by",
    "is_light",
    "limits",
    "read_configuration",
    "readback",
]


@runtime_checkable
class Axis(AsyncLocatable[float], Subscribable[float], Protocol):
    """Something `set` moves, `locate` reports and `subscribe_reading` follows.

    `set` returns an `ophyd-async` status, which the positioner waits on and
    cancels to stop the move. Checking an object against this protocol at run
    time finds the methods only, not what `set` returns.
    """

    def set(self, value: float, /) -> AsyncStatus[Any] | WatchableAsyncStatus[float]:
        """Start a move to *value*, which is passed by position.

        An axis may name the parameter as it likes, `new_position` for an
        `ophyd-async` `StandardMovable`.
        """
        ...


@dataclass(frozen=True, slots=True)
class Readback:
    """A number as a device reads it back, with what its descriptor says of it."""

    value: float
    """The value read."""

    units: str | None = None
    """Engineering units, from the descriptor."""

    precision: int | None = None
    """Decimals the descriptor asks for."""

    limits: tuple[float | None, float | None] = (None, None)
    """Lowest and highest value the descriptor allows; `None` for no bound."""


@dataclass(frozen=True, slots=True)
class AxisInfo:
    """What a view shows of an axis before its next readback arrives."""

    readback: Readback
    """Position when the axis was described, with its units, precision and limits."""

    stoppable: bool = False
    """Whether the axis can be stopped, by itself or through its device."""

    key: str | None = None
    """Data key of the readback in the readings the axis reports."""

    configuration: tuple[str, ...] = ()
    """Keys of the axis' configuration entries."""

    path: DevicePath | None = None
    """Where the axis sits in its tree; `None` when not known."""


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

    paths: dict[str, DevicePath] = field(default_factory=dict)
    """Where the signal behind each key, and each owner, sit in their tree, by name.

    Empty when not known.
    """


class DevicePath(NamedTuple):
    """Where a device sits in its tree."""

    root: str
    """Name of the device the keys start from: the top of the tree, or the
    highest device below a parent that does not list it among its children."""

    keys: tuple[str, ...]
    """Key of each device below the root, down to this one; empty for the root."""

    names: tuple[str, ...]
    """Names of the device at the top of the tree and of every device down to
    this one, in order."""

    @property
    def path(self) -> str:
        """The keys joined by dots, such as `xy.x`; empty for the root."""
        return ".".join(self.keys)

    @property
    def parent(self) -> DevicePath | None:
        """Where the device's parent sits; `None` for a root."""
        if not self.keys:
            return None
        return DevicePath(self.root, self.keys[:-1], self.names[:-1])

    def __str__(self) -> str:
        """Return the label a view shows: `scope / xy.x`, or `scope` for a root."""
        return f"{self.root} / {self.path}" if self.keys else self.root


def device_path(device: Device) -> DevicePath:
    """Return where *device* sits in its tree.

    A device whose parent does not list it among its children starts the
    keys, as a root does, and the names still reach the top of the tree.
    """
    keys: list[str] = []
    names = [device.name]
    root = device.name
    listed = True
    child = device
    while (parent := child.parent) is not None:
        names.append(parent.name)
        key = next((str(k) for k, each in parent.children() if each is child), None)
        listed = listed and key is not None
        if listed:
            keys.append(str(key))
            root = parent.name
        child = parent
    return DevicePath(root, tuple(reversed(keys)), tuple(reversed(names)))


def held_by(device: Device, names: AbstractSet[str]) -> bool:
    """Tell whether *device* or a device above it is in *names*."""
    current: Device | None = device
    while current is not None:
        if current.name in names:
            return True
        current = current.parent
    return False


def is_axis(item: object) -> TypeGuard[Axis]:
    """Tell whether *item* is an axis: one that is not a signal."""
    return isinstance(item, Axis) and not isinstance(item, Signal)


def readback(value: float, descriptor: Mapping[str, Any]) -> Readback:
    """Return *value* with the units, precision and limits *descriptor* gives.

    Units that are not text, and a precision that is not a whole number of at
    least 0, are left out.
    """
    units = descriptor.get("units")
    precision = descriptor.get("precision")
    return Readback(
        value=value,
        units=units if isinstance(units, str) else None,
        precision=precision
        if isinstance(precision, int)
        and not isinstance(precision, bool)
        and precision >= 0
        else None,
        limits=limits(descriptor),
    )


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
    readable has none.

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
    return AxisInfo(
        readback=readback(float(position), descriptor),
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
    """What a view shows of a light before its next readback arrives."""

    enabled: bool
    """Whether the light was on when described."""

    intensity: Readback | None = None
    """Intensity when described, with its units, precision and limits; `None` for a
    light that has none."""

    path: DevicePath | None = None
    """Where the light sits in its tree; `None` when not known."""


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
    intensity = readback(float(value), described.get(light.intensity.name, {}))
    if whole:
        intensity = dataclasses.replace(intensity, precision=0)
    return LightInfo(enabled=bool(enabled), intensity=intensity)
