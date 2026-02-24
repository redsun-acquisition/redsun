from __future__ import annotations

from typing import TYPE_CHECKING

from redsun.storage.zarr import ZarrWriter

if TYPE_CHECKING:
    from redsun.storage._base import Writer
    from redsun.storage._prepare import StorageInfo


def make_writer(name: str, info: StorageInfo) -> Writer:
    device_info = info.devices.get(name)
    format_hint = (
        device_info.format_hint if device_info is not None else "application/x-zarr"
    )
    if format_hint == "application/x-zarr":
        return ZarrWriter(info)
    raise ValueError(f"Unsupported format hint: {format_hint!r}")
