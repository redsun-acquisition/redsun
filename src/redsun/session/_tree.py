from __future__ import annotations

from typing import TYPE_CHECKING

from ophyd_async.core import Command, Signal, walk_devices

from redsun.errors import BuildError

if TYPE_CHECKING:
    from collections.abc import Iterable

    from ophyd_async.core import Device


def index_devices(roots: Iterable[Device]) -> dict[str, Device]:
    """Return every device of the trees under *roots* by name.

    Signals and commands are left out.

    Raises
    ------
    BuildError
        If two devices share a name, or a device has none.
    """
    index: dict[str, Device] = {}
    places: dict[str, str] = {}
    for root in roots:
        for path, device in [("", root), *walk_devices(root).items()]:
            if isinstance(device, (Signal, Command)):
                continue
            place = f"{root.name}.{path}" if path else root.name
            if not device.name:
                raise BuildError(f"The device at {place!r} has no name")
            if device.name in index:
                raise BuildError(
                    f"Two devices are named {device.name!r}: "
                    f"{places[device.name]!r} and {place!r}"
                )
            index[device.name] = device
            places[device.name] = place
    return index
