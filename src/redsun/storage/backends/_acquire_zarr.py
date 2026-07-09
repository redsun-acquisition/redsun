from __future__ import annotations

from typing import TYPE_CHECKING

import acquire_zarr as az

from redsun.storage import StorageBackend

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from typing import Any, Final

    import numpy.typing as npt
    from ophyd_async.core import PathProvider

    from redsun.storage import StreamSpec


class AcquireZarrBackend(StorageBackend):
    """Storage backend for Zarr files using the `acquire-zarr` library."""

    mimetype = "application/x-zarr"
    extension = "zarr"

    _DTYPE_MAP: Final[dict[str, az.DataType]] = {
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

    def __init__(self, path_provider: PathProvider) -> None:
        self._stream: az.ZarrStream | None = None
        self._settings: dict[str, list[az.Dimension]] = {}
        self.path_provider = path_provider

    async def _frame_pusher(
        self, data_key: str
    ) -> AsyncGenerator[None, npt.NDArray[Any]]:
        """Create a generator that accepts frames and stores them in the Zarr stream for the given data key."""
        await self.ensure_open(data_key)
        if self._stream is None:
            raise RuntimeError("Zarr stream is not initialized.")
        try:
            while True:
                frame = yield
                # Here you would write the frame to the Zarr stream
                # For example: self._stream.write(data_key, frame)
                # This is a placeholder for the actual implementation
                frame
        except GeneratorExit:
            await self.release(data_key)

    async def __call__(self, data_key: str) -> AsyncGenerator[None, npt.NDArray[Any]]:
        gen = self._frame_pusher(data_key)
        await anext(gen)
        return gen

    async def register(self, spec: StreamSpec) -> None:
        t = spec.capacity if spec.capacity is not None else 0
        x, y = spec.shape
        # TODO: add the ability to customize these
        # settings from the spec... somehow
        chunk_size_x = x // 4 if x >= 4 else 1
        chunk_size_y = y // 4 if y >= 4 else 1
        shard_size_chunks = 2
        self._settings[spec.data_key] = [
            az.Dimension(
                name="t",
                kind=az.DimensionType.TIME,
                array_size_px=t,
                chunk_size_px=1,
                shard_size_chunks=shard_size_chunks,
            ),
            az.Dimension(
                name="y",
                kind=az.DimensionType.SPACE,
                array_size_px=x,
                chunk_size_px=chunk_size_y,
                shard_size_chunks=shard_size_chunks,
            ),
            az.Dimension(
                name="x",
                kind=az.DimensionType.SPACE,
                array_size_px=y,
                chunk_size_px=chunk_size_x,
                shard_size_chunks=shard_size_chunks,
            ),
        ]
        self.router.add(spec)

    async def ensure_open(self, data_key: str) -> None: ...

    async def release(self, data_key: str) -> None:
        pass
