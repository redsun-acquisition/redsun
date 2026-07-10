from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import acquire_zarr as az
import numpy as np
from ophyd_async.core import StreamResourceInfo

from .._base import OpenStore, StorageIO

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Any, Final

    import numpy.typing as npt
    from ophyd_async.core import PathInfo

    from .._base import StreamSpec

DTYPE_MAP: Final[dict[str, az.DataType]] = {
    "uint8": az.DataType.UINT8,
    "uint16": az.DataType.UINT16,
    "uint32": az.DataType.UINT32,
    "uint64": az.DataType.UINT64,
    "int8": az.DataType.INT8,
    "int16": az.DataType.INT16,
    "int32": az.DataType.INT32,
    "int64": az.DataType.INT64,
    "float32": az.DataType.FLOAT32,
    "float64": az.DataType.FLOAT64,
}


class AcquireZarrIO(StorageIO):
    """Zarr storage backend through [`acquire-zarr`](https://acquire-project.github.io/acquire-docs/stable/).

    A single Zarr store holds one array per registered data key
    (via `output_key`), so all detectors of a burst land in the same
    store under distinct keys.

    Chunking policy is fixed at construction: spatial chunks are
    `dimension // chunk_divisor` (at least 1 pixel), the time chunk is
    `chunk_t` frames, sharding is `shard_size_chunks` chunks per shard.

    Parameters
    ----------
    chunk_divisor : int
        Divisor for spatial chunk sizes. Defaults to 4
        (i.e. 4x4 chunks per frame).
    chunk_t : int
        Chunk size along the time axis, in frames. Defaults to 1.
    shard_size_chunks : int
        Number of chunks per shard, per axis. Defaults to 2.
    """

    mimetype = "application/x-zarr"
    extension = "zarr"

    __slots__ = ("_chunk_divisor", "_chunk_t", "_shard_size_chunks")

    def __init__(
        self, *, chunk_divisor: int = 4, chunk_t: int = 1, shard_size_chunks: int = 2
    ) -> None:
        self._chunk_divisor = chunk_divisor
        self._chunk_t = chunk_t
        self._shard_size_chunks = shard_size_chunks

    async def open(self, path: PathInfo, specs: Mapping[str, StreamSpec]) -> OpenStore:
        """Open a Zarr store for writing."""
        settings = az.StreamSettings()
        settings.store_path = str(
            Path(path.directory_path) / f"{path.filename}.{self.extension}"
        )
        settings.arrays = [self._array_settings(spec) for spec in specs.values()]
        stream = az.ZarrStream(settings)
        return AcquireZarrStore(stream)

    def _spatial_chunks(self, spec: StreamSpec) -> tuple[int, int]:
        """Spatial chunk sizes for a spec. Single source for dimensions and documents."""
        height, width = spec.shape
        return (
            max(1, height // self._chunk_divisor),
            max(1, width // self._chunk_divisor),
        )

    def uri(self, path: PathInfo, data_key: str) -> str:
        """Return a URI for a data key in a Zarr store."""
        return f"{path.directory_uri}{path.filename}.{self.extension}"

    def resource_info(self, spec: StreamSpec) -> StreamResourceInfo:
        """Describe the stream with the true on-disk chunk layout."""
        chunk_y, chunk_x = self._spatial_chunks(spec)
        return StreamResourceInfo(
            data_key=spec.data_key,
            shape=spec.shape,
            chunk_shape=(self._chunk_t, chunk_y, chunk_x),
            dtype_numpy=np.dtype(spec.dtype).str,
            parameters={"path": spec.data_key},
        )

    def _array_settings(self, spec: StreamSpec) -> az.ArraySettings:
        height, width = spec.shape
        chunk_y, chunk_x = self._spatial_chunks(spec)
        t_size = spec.capacity if spec.capacity is not None else 0
        settings = az.ArraySettings()
        settings.output_key = spec.data_key
        settings.data_type = DTYPE_MAP[np.dtype(spec.dtype).name]
        settings.dimensions = [
            az.Dimension(
                name="t",
                kind=az.DimensionType.TIME,
                array_size_px=t_size,
                chunk_size_px=self._chunk_t,
                shard_size_chunks=self._shard_size_chunks,
            ),
            az.Dimension(
                name="y",
                kind=az.DimensionType.SPACE,
                array_size_px=height,
                chunk_size_px=chunk_y,
                shard_size_chunks=self._shard_size_chunks,
            ),
            az.Dimension(
                name="x",
                kind=az.DimensionType.SPACE,
                array_size_px=width,
                chunk_size_px=chunk_x,
                shard_size_chunks=self._shard_size_chunks,
            ),
        ]
        return settings


class AcquireZarrStore(OpenStore):
    """Open Zarr store wrapping an `acquire_zarr.ZarrStream`."""

    __slots__ = ("_stream",)

    def __init__(self, stream: az.ZarrStream) -> None:
        self._stream = stream

    async def write(self, data_key: str, frame: npt.NDArray[Any]) -> None:
        """Write a single frame to the Zarr store."""
        self._stream.append(frame, data_key)

    async def release(self, data_key: str) -> None:
        # no-op, acquire-zarr closes
        # and flushes on context exit
        ...

    async def close(self) -> None:
        self._stream.close()
