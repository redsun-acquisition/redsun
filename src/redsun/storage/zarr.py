"""Zarr-based storage writer using acquire-zarr."""

from __future__ import annotations

from typing import TYPE_CHECKING

from redsun.storage._base import FrameSink, Writer
from redsun.storage.utils import from_uri

try:
    from acquire_zarr import (
        ArraySettings,
        Dimension,
        DimensionType,
        StreamSettings,
        ZarrStream,
    )

    _ACQUIRE_ZARR_AVAILABLE = True
except ImportError:
    _ACQUIRE_ZARR_AVAILABLE = False


if TYPE_CHECKING:
    import numpy as np
    import numpy.typing as npt

    from redsun.storage._prepare import StorageInfo


class ZarrWriter(Writer):
    """Zarr storage backend using `acquire-zarr`.

    Writes detector frames to a Zarr v3 store. Each `ZarrWriter` instance
    is owned by a single device and writes to the URI provided in the
    [`StorageInfo`][redsun.storage.StorageInfo] it receives on construction.

    Parameters
    ----------
    info : StorageInfo
        Fully resolved storage location. The store URI is read from
        `info.uri`; device metadata from `info.devices` is available
        to subclasses for format-specific configuration.
    """

    def __init__(self, info: StorageInfo) -> None:
        if not _ACQUIRE_ZARR_AVAILABLE:
            raise ImportError(
                "ZarrWriter requires the 'acquire-zarr' package. "
                "Install it with: pip install redsun[zarr]"
            )
        super().__init__(info)
        self._stream_settings = StreamSettings()
        self._stream_settings.store_path = from_uri(info.uri)
        self._array_settings: dict[str, ArraySettings] = {}

    @property
    def mimetype(self) -> str:
        """Return the MIME type for Zarr storage."""
        return "application/x-zarr"

    def prepare(self, name: str, capacity: int = 0) -> FrameSink:
        """Prepare Zarr storage for *name* and return a frame sink.

        Pre-declares spatial and temporal dimensions for the source and
        returns a [`FrameSink`][redsun.storage.FrameSink] bound to *name*.

        Parameters
        ----------
        name : str
            Source name (device name).
        capacity : int
            Maximum frames (`0` = unlimited).

        Returns
        -------
        FrameSink
            Bound sink; call `sink.write(frame)` to push frames.
        """
        source = self._sources[name]
        height, width = source.shape

        dimensions = [
            Dimension(
                name="t",
                kind=DimensionType.TIME,
                array_size_px=capacity,
                chunk_size_px=1,
                shard_size_chunks=2,
            ),
            Dimension(
                name="y",
                kind=DimensionType.SPACE,
                array_size_px=height,
                chunk_size_px=max(1, height // 4),
                shard_size_chunks=2,
            ),
            Dimension(
                name="x",
                kind=DimensionType.SPACE,
                array_size_px=width,
                chunk_size_px=max(1, width // 4),
                shard_size_chunks=2,
            ),
        ]
        self._array_settings[name] = ArraySettings(
            dimensions=dimensions,
            data_type=source.dtype,
            output_key=source.name,
        )

        return super().prepare(name, capacity)

    def kickoff(self) -> None:
        """Open the Zarr stream for writing. No-op if already open."""
        if self.is_open:
            return
        self._stream_settings.arrays = list(self._array_settings.values())
        self._stream = ZarrStream(self._stream_settings)
        super().kickoff()

    def _finalize(self) -> None:
        """Close the Zarr stream."""
        self._stream.close()

    def _write_frame(self, name: str, frame: npt.NDArray[np.generic]) -> None:
        """Append *frame* to the Zarr stream under the array key for *name*."""
        self._stream.append(frame, key=name)
