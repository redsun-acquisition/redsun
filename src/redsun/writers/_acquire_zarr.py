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
    from collections.abc import Mapping
    from pathlib import Path

    from numpy.typing import NDArray

    from ._base import ArrayShape

_SPATIAL = frozenset({"z", "y", "x"})


class Stream:
    """A Zarr store open for appending frames to a set of keys.

    Every key is declared at open, since `acquire-zarr` sizes a store's
    arrays once. A key that exists in the store already is refused.
    """

    __slots__ = ("_arrays", "_path", "_stream")

    def __init__(
        self, path: Path, arrays: Mapping[str, ArrayShape], *, is_ngff: bool
    ) -> None:
        settings = az.StreamSettings()
        settings.store_path = str(path)
        settings.overwrite = False
        settings.arrays = [
            array_settings(data_key, layout, is_ngff=is_ngff)
            for data_key, layout in arrays.items()
        ]
        self._path = path
        self._arrays = dict(arrays)
        self._stream = az.ZarrStream(settings)

    def append(self, data_key: str, data: NDArray[Any]) -> None:
        """Append one frame, or a stack of frames, to *data_key*.

        Raises
        ------
        WriterError
            If the stream was not opened with *data_key*, or *data* does not
            match its layout.
        """
        layout = self._arrays.get(data_key)
        if layout is None:
            raise WriterError(
                f"{data_key!r} is not an array of the stream on {self._path}, "
                f"which was opened with {sorted(self._arrays)}"
            )
        self._stream.append(layout.check(data_key, data), data_key)

    def node(self, data_key: str) -> Path:
        """Return the path of the group holding *data_key*."""
        return self._path / data_key

    def close(self) -> None:
        """Finish every array; nothing can be appended afterwards."""
        self._stream.close()


def array_settings(
    data_key: str, layout: ArrayShape, *, is_ngff: bool
) -> az.ArraySettings:
    """Return the `acquire-zarr` settings of an array of frames shaped *layout*.

    The appended axis leads, sized as it grows and chunked one frame at a time.
    """
    names = axis_names(len(layout.shape) + 1)
    array = az.ArraySettings()
    array.output_key = data_key
    array.is_ngff = is_ngff
    array.data_type = _data_type(layout.dtype)
    array.dimensions = [
        az.Dimension(
            name=name,
            kind=_kind(name),
            array_size_px=0 if index == 0 else size,
            chunk_size_px=1 if index == 0 else size,
            shard_size_chunks=1,
        )
        for index, (name, size) in enumerate(
            zip(names, (0, *layout.shape), strict=True)
        )
    ]
    return array


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
