from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

from redsun.storage.writers._base import WriterError, axis_names, require

if TYPE_CHECKING:
    from pathlib import Path

    from numpy.typing import NDArray

_SPATIAL = frozenset({"z", "y", "x"})


def append_key(path: Path, *, data_key: str, data: NDArray[Any], is_ngff: bool) -> None:
    """Write *data* as a new key of the store at *path*, through `acquire-zarr`.

    The array is written in one append. A leading axis is added to a 2D array,
    since the first axis is the one a stream appends along.
    """
    az = require("acquire_zarr", extra="zarr")
    if data.ndim == 2:
        data = data[None]
    names = axis_names(data.ndim)

    array = az.ArraySettings()
    array.output_key = data_key
    array.is_ngff = is_ngff
    array.data_type = _data_type(az, data.dtype)
    array.dimensions = [
        az.Dimension(
            name=name,
            kind=_kind(az, name),
            # the first axis is the appended one, and is sized as it grows
            array_size_px=0 if index == 0 else size,
            chunk_size_px=1 if index == 0 else size,
            shard_size_chunks=1,
        )
        for index, (name, size) in enumerate(zip(names, data.shape, strict=True))
    ]

    settings = az.StreamSettings()
    settings.store_path = str(path)
    settings.overwrite = False
    settings.arrays = [array]

    stream = az.ZarrStream(settings)
    try:
        stream.append(data, data_key)
    finally:
        stream.close()


def _kind(az: Any, name: str) -> Any:
    """Return the `acquire-zarr` dimension type of the NGFF axis *name*."""
    if name in _SPATIAL:
        return az.DimensionType.SPACE
    if name == "c":
        return az.DimensionType.CHANNEL
    return az.DimensionType.TIME


def _data_type(az: Any, dtype: np.dtype[Any]) -> Any:
    """Return the `acquire-zarr` data type matching *dtype*."""
    try:
        return getattr(az.DataType, np.dtype(dtype).name.upper())
    except AttributeError as e:
        raise WriterError(f"acquire-zarr cannot write arrays of {dtype}") from e
