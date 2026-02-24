from __future__ import annotations

from typing import TYPE_CHECKING

from redsun.storage.zarr import ZarrWriter

if TYPE_CHECKING:
    from redsun.storage._base import Writer
    from redsun.storage._info import StorageInfo


def make_writer(name: str, info: StorageInfo) -> Writer:
    device_info = info.devices.get(name)
    mimetype = device_info.mimetype if device_info is not None else "application/x-zarr"
    if mimetype == "application/x-zarr":
        return ZarrWriter(info)
    raise ValueError(f"Unsupported format hint: {mimetype!r}")
