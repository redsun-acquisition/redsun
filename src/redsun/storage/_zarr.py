from __future__ import annotations

from itertools import count
from typing import TYPE_CHECKING, Any

from redsun.storage import DataWriter

try:
    import acquire_zarr as az

    _ACQUIRE_ZARR_AVAILABLE = True
except ImportError:
    _ACQUIRE_ZARR_AVAILABLE = False

if TYPE_CHECKING:
    from pathlib import PurePath
    from typing import Any

    import numpy.typing as npt

    from redsun.storage import SourceInfo

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


class ZarrDataWriter(DataWriter):
    """[`acquire-zarr`](https://acquire-project.github.io/acquire-docs/stable/) data writer."""

    def __init__(self) -> None:
        if not _ACQUIRE_ZARR_AVAILABLE:
            raise ImportError(
                "ZarrDataWriter requires the 'acquire-zarr' package. "
                "Install it with: pip install redsun[zarr]"
            )
        self._stream_settings = az.StreamSettings()
        self._array_settings: dict[str, az.ArraySettings] = {}
        self._stream: az.ZarrStream | None = None
        self._sources: dict[str, SourceInfo] = {}
        self._metadata: dict[str, Any] = {}
        self._counter = count()

    @property
    def is_open(self) -> bool:
        return self._stream is not None and self._stream.is_active()

    @property
    def metadata(self) -> dict[str, Any]:
        return self._metadata

    @metadata.setter
    def metadata(self, value: dict[str, object]) -> None:
        self._metadata.update(value)

    @property
    def sources(self) -> dict[str, SourceInfo]:
        return self._sources

    @property
    def mimetype(self) -> str:
        return "application/x-zarr"

    @property
    def file_extension(self) -> str:
        return "zarr"

    # TODO: the dimension settings should be configurable,
    # possibly from the presenter side. So the API should
    # allow the presenter to specify the dimension types and chunk sizes.
    # Maybe a per-backend dataclass with specific settings
    # that the presenter/view can populate and pass to the writer?
    def register(self, datakey: str, info: SourceInfo) -> None:

        # acquire-zarr uses 0 to indicate unlimited capacity
        actual_capacity = info.capacity if info.capacity is not None else 0
        height, width = info.shape

        dimensions = [
            az.Dimension(
                name="t",
                kind=az.DimensionType.TIME,
                array_size_px=actual_capacity,
                chunk_size_px=1,
                shard_size_chunks=2,
            ),
            az.Dimension(
                name="y",
                kind=az.DimensionType.SPACE,
                array_size_px=height,
                chunk_size_px=max(1, height // 4),
                shard_size_chunks=2,
            ),
            az.Dimension(
                name="x",
                kind=az.DimensionType.SPACE,
                array_size_px=width,
                chunk_size_px=max(1, width // 4),
                shard_size_chunks=2,
            ),
        ]

        self._array_settings[datakey] = az.ArraySettings(
            dimensions=dimensions,
            data_type=DTYPE_MAP[info.dtype_numpy],
            output_key=datakey,
        )
        self._sources[datakey] = info

    def unregister(self, datakey: str) -> None:
        self._array_settings.pop(datakey, None)
        self._sources.pop(datakey, None)

    def open(self, path: PurePath) -> None:
        if self._stream is not None and self._stream.is_active():
            raise RuntimeError(
                f"Stream is already open at {self._stream_settings.store_path!r}."
            )
        try:
            self._stream_settings.store_path = str(path)
            self._stream_settings.arrays = list(self._array_settings.values())
            self._stream = az.ZarrStream(self._stream_settings)
        except Exception as e:
            raise e

    def close(self) -> None:
        # need to make sure that
        # the stream is both open
        # and sources have been
        # unregistered before closing
        if (
            self._stream is not None
            and self._stream.is_active()
            and len(self.sources) == 0
        ):
            self._stream.close()
            self._stream = None
        else:
            err_msg = ""
            if self._stream is None or not self._stream.is_active():
                err_msg = "Stream is not open."
            if len(self.sources) > 0:
                err_msg = "Sources are still registered."
            raise RuntimeError(err_msg)
        self._array_settings.clear()
        self._counter = count()

    def write(self, datakey: str, data: npt.NDArray[Any]) -> None:
        if self._stream is None:
            raise RuntimeError("Stream is not open. Call open() before writing.")
        self._stream.append(data, key=datakey)
        self._update_count(next(self._counter))


__all__ = ["ZarrDataWriter"]
