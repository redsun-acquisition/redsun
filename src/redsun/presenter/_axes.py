"""The axes of a device: its parts that can be moved, found by protocol."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Protocol, TypeGuard, runtime_checkable

from bluesky.protocols import Subscribable
from ophyd_async.core import AsyncLocatable, Signal

if TYPE_CHECKING:
    from collections.abc import Iterator

    from ophyd_async.core import Device


@runtime_checkable
class Axis(AsyncLocatable[float], Subscribable[float], Protocol):
    """Something `set` moves, `locate` reports and `subscribe` follows."""


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
    Otherwise its descendants are walked, and each axis is keyed by its
    attribute name, or by its dotted path when another axis of the device
    shares that name. A signal is never an axis, though a writable one can
    be set and located.
    """
    if is_axis(device):
        return {device.name: device}
    found = dict(walk_axes(device))
    names = Counter(path.rpartition(".")[2] for path in found)
    return {
        path if names[path.rpartition(".")[2]] > 1 else path.rpartition(".")[2]: axis
        for path, axis in found.items()
    }
