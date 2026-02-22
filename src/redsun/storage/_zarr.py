# SPDX-License-Identifier: Apache-2.0
# The design of this module is heavily inspired by ophyd-async
# (https://github.com/bluesky/ophyd-async), developed by the Bluesky collaboration.
# ophyd-async is licensed under the BSD 3-Clause License.
# No source code from ophyd-async has been copied; the backend writer pattern
# was studied and independently re-implemented using acquire-zarr for redsun.

"""Zarr-based storage writer using acquire-zarr."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003
from typing import TYPE_CHECKING

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

from redsun.storage._base import FrameSink, Writer

if TYPE_CHECKING:
    import numpy as np
    import numpy.typing as npt

    from redsun.storage._path import PathProvider


class ZarrWriter(Writer):
    """Zarr storage backend using `acquire-zarr`.

    Writes detector frames to a Zarr v3 store.  Multiple devices share
    one `ZarrWriter` instance; each device is assigned its own array
    within the store, keyed by device name.

    The store URI is resolved by the
    [`PathProvider`][redsun.storage.PathProvider]
    supplied at construction time.  Devices call
    [`Writer.prepare`][redsun.storage.Writer.prepare] without any path
    arguments — path resolution is entirely internal.

    Parameters
    ----------
    name : str
        Unique name for this writer (used for logging).
    path_provider : PathProvider
        Callable that returns [`PathInfo`][redsun.storage.PathInfo] for each
        device.  Called once per device per
        [`prepare`][redsun.storage.Writer.prepare] invocation.
    base_dir : Path
        Filesystem directory under which all stores for this writer are
        created.  ``kickoff()`` ensures this directory exists before
        opening the stream, so the caller does not need to ``mkdir`` it
        in advance.
    """

    def __init__(self, name: str, path_provider: PathProvider, base_dir: Path) -> None:
        if not _ACQUIRE_ZARR_AVAILABLE:
            raise ImportError(
                "ZarrWriter requires the 'acquire-zarr' package. "
                "Install it with: pip install redsun[zarr]"
            )
        super().__init__(name)
        self._path_provider = path_provider
        self._base_dir = base_dir
        self._stream_settings = StreamSettings()
        self._dimensions: dict[str, list[Dimension]] = {}
        self._array_settings: dict[str, ArraySettings] = {}

    @property
    def mimetype(self) -> str:
        """Return the MIME type for Zarr storage."""
        return "application/x-zarr"

    def prepare(self, name: str, capacity: int = 0) -> FrameSink:
        """Prepare Zarr storage for *name* and return a frame sink.

        Resolves the store path via the
        [`PathProvider`][redsun.storage.PathProvider],
        pre-declares spatial and temporal dimensions for the source, and
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
        path_info = self._path_provider(name)
        self._store_path = path_info.store_uri
        self._stream_settings.store_path = path_info.store_uri

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
        self._dimensions[name] = dimensions
        self._array_settings[name] = ArraySettings(
            dimensions=dimensions,
            data_type=source.dtype,
            output_key=source.name,
        )

        return super().prepare(name, capacity)

    def kickoff(self) -> None:
        """Open the Zarr stream for writing.  No-op if already open."""
        if self.is_open:
            return
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._stream_settings.arrays = list(self._array_settings.values())
        self._stream = ZarrStream(self._stream_settings)
        super().kickoff()

    def _finalize(self) -> None:
        """Close the Zarr stream."""
        self._stream.close()

    def _write_frame(self, name: str, frame: npt.NDArray[np.generic]) -> None:
        """Append *frame* to the Zarr stream under the array key for *name*."""
        self._stream.append(frame, key=name)
