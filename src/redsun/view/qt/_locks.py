from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Set as AbstractSet

    from redsun.utils.devices import DevicePath


def held(path: DevicePath | None, key: str, names: AbstractSet[str]) -> bool:
    """Tell whether *names* holds a device on *path*, or *key* when there is none."""
    if path is None:
        return key in names
    return any(name in names for name in path.names)
