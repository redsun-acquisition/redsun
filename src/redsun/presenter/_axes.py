"""The axes of a device: its parts that can be moved, found by protocol."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, TypeGuard, runtime_checkable

from bluesky.protocols import Subscribable
from ophyd_async.core import AsyncLocatable, Signal

if TYPE_CHECKING:
    from ophyd_async.core import Device


@runtime_checkable
class Axis(AsyncLocatable[float], Subscribable[float], Protocol):
    """Something `set` moves, `locate` reports and `subscribe` follows."""


def is_axis(item: object) -> TypeGuard[Axis]:
    """Tell whether *item* is an axis: one that is not a signal."""
    return isinstance(item, Axis) and not isinstance(item, Signal)


def find_axes(device: Device) -> dict[str, Axis]:
    """Return the axes of *device*, by name.

    A device that is itself an axis is its only axis, under its own name.
    Otherwise its descendants are searched, and the search stops at each axis
    it finds, so the signals of an axis are never axes. An axis is keyed by
    its attribute name, and by its dotted path when another axis of the
    device shares that name. A signal is never an axis, though a writable
    one can be set and located.
    """
    if is_axis(device):
        return {device.name: device}
    found: list[tuple[tuple[str, ...], Axis]] = []

    def search(node: Device, path: tuple[str, ...]) -> None:
        for name, child in node.children():
            if is_axis(child):
                found.append(((*path, name), child))
            elif not isinstance(child, Signal):
                search(child, (*path, name))

    search(device, ())
    names = [path[-1] for path, _ in found]
    return {
        path[-1] if names.count(path[-1]) == 1 else ".".join(path): axis
        for path, axis in found
    }
