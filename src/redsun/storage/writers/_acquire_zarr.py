from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

from ._base import WriterError, axis_names

try:
    import acquire_zarr as az
except ImportError as error:
    raise ImportError(
        "acquire-zarr is needed to write a Zarr product and is not installed; "
        "install it with 'pip install redsun[zarr]'"
    ) from error

if TYPE_CHECKING:
    from pathlib import Path

    from numpy.typing import NDArray

_SPATIAL = frozenset({"z", "y", "x"})


def append_key(path: Path, *, data_key: str, data: NDArray[Any], is_ngff: bool) -> None:
    """Write *data* as a new key of the store at *path*, in one `acquire-zarr` append.

    A 2D array gets a leading axis, the one a stream appends along.
    """
    if data.ndim == 2:
        data = data[None]
    names = axis_names(data.ndim)

    array = az.ArraySettings()
    array.output_key = data_key
    array.is_ngff = is_ngff
    array.data_type = _data_type(data.dtype)
    array.dimensions = [
        az.Dimension(
            name=name,
            kind=_kind(name),
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


def _kind(name: str) -> az.DimensionType:
    """Return the `acquire-zarr` dimension type of the NGFF axis *name*."""
    if name in _SPATIAL:
        return az.DimensionType.SPACE
    if name == "c":
        return az.DimensionType.CHANNEL
    return az.DimensionType.TIME


def _data_type(dtype: np.dtype[Any]) -> az.DataType:
    """Return the `acquire-zarr` data type matching *dtype*."""
    match np.dtype(dtype).name:
        case "uint8":
            return az.DataType.UINT8
        case "uint16":
            return az.DataType.UINT16
        case "uint32":
            return az.DataType.UINT32
        case "uint64":
            return az.DataType.UINT64
        case "int8":
            return az.DataType.INT8
        case "int16":
            return az.DataType.INT16
        case "int32":
            return az.DataType.INT32
        case "int64":
            return az.DataType.INT64
        case "float32":
            return az.DataType.FLOAT32
        case "float64":
            return az.DataType.FLOAT64
        case name:
            raise WriterError(f"acquire-zarr cannot write arrays of {name}")
