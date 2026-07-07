from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from redsun.log import Loggable
from redsun.storage.utils import from_uri

from ._base import BaseDataStore

try:
    from typing import Any

    import acquire_zarr as az
    import numpy.typing as npt

    DTYPE_MAP: dict[str, az.DataType] = {
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

except ImportError:
    raise ImportError(
        "The `acquire-zarr` package is required for ZarrDataStore. "
        "Please install it with `pip install redsun[zarr]`."
    )

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ophyd_async.core import PathProvider

    from redsun.storage._base import StreamSpec


class ZarrDataStore(BaseDataStore, Loggable):
    """Implementation of a Zarr-based data store through [`acquire-zarr`](https://acquire-project.github.io/acquire-docs/stable/)."""

    @property
    def mimetype(self) -> str:
        """The MIME type of the data store, e.g. ``"application/x-hdf5"``."""
        return "application/x-zarr"

    @property
    def extension(self) -> str:
        """The file extension for the data store, e.g. ``"zarr"``."""
        return "zarr"

    def __init__(self, path_provider: PathProvider) -> None:
        super().__init__(path_provider)
        self._stream: az.ZarrStream | None = None

    def _array_settings(self, spec: StreamSpec) -> az.ArraySettings:
        height, width = spec.shape
        p = spec.parameters
        shard = int(p.get("shard_chunks", 2))
        # capacity None -> unbounded time axis (0 array_size_px in acquire-zarr).
        t_size = spec.capacity if spec.capacity is not None else 0
        dimensions = [
            az.Dimension(
                name="t",
                kind=az.DimensionType.TIME,
                array_size_px=t_size,
                chunk_size_px=int(p.get("chunk_t", 1)),
                shard_size_chunks=shard,
            ),
            az.Dimension(
                name="y",
                kind=az.DimensionType.SPACE,
                array_size_px=height,
                chunk_size_px=int(p.get("chunk_y", max(1, height // 4))),
                shard_size_chunks=shard,
            ),
            az.Dimension(
                name="x",
                kind=az.DimensionType.SPACE,
                array_size_px=width,
                chunk_size_px=int(p.get("chunk_x", max(1, width // 4))),
                shard_size_chunks=shard,
            ),
        ]
        return az.ArraySettings(
            dimensions=dimensions,
            data_type=DTYPE_MAP[np.dtype(spec.dtype_numpy).name],
            output_key=spec.data_key,
        )

    async def _backend_open(self, uri: str, specs: Sequence[StreamSpec]) -> None:
        settings = az.StreamSettings()
        settings.store_path = from_uri(uri)
        settings.arrays = [self._array_settings(s) for s in specs]
        self._stream = az.ZarrStream(settings)
        self.logger.debug(
            "Opened zarr store at %s with keys %s",
            settings.store_path,
            [s.data_key for s in specs],
        )

    async def _backend_write(self, key: str, frame: npt.NDArray[Any]) -> None:
        if self._stream is None:
            raise RuntimeError("Zarr stream is not open.")
        self._stream.append(frame, key)

    async def _backend_close(self) -> None:
        if self._stream is not None:
            self._stream.close()
            self.logger.debug("Closed zarr store.")
            self._stream = None


__all__ = ["ZarrDataStore"]
