"""Zarr-based storage writer using acquire-zarr."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from redsun.storage._base import Writer
from redsun.storage.metadata import clear_metadata
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


class ZarrWriter(Writer):
    """Zarr storage backend using ``acquire-zarr``.

    Writes detector frames to a Zarr v3 store via ``acquire-zarr``'s
    ``ZarrStream``.  All devices that share the same store group name
    contribute their sources to a single ``ZarrStream`` instance, so
    their arrays land in one Zarr store on disk.

    The store path is not known at construction time.  It is supplied
    (and can be updated between acquisitions) via
    [`set_uri`][redsun.storage.Writer.set_uri], which rebuilds
    ``StreamSettings.store_path`` without disturbing registered sources
    or the registry entry.

    Parameters
    ----------
    name : str
        Store group name.  See [`Writer`][redsun.storage.Writer] for
        full semantics.  Defaults to ``"default"``.
    """

    def __init__(self, name: str = "default") -> None:
        if not _ACQUIRE_ZARR_AVAILABLE:
            raise ImportError(
                "ZarrWriter requires the 'acquire-zarr' package. "
                "Install it with: pip install redsun[zarr]"
            )
        super().__init__(name)
        self._stream_settings = StreamSettings()
        self._array_settings: dict[str, ArraySettings] = {}
        self._stream: ZarrStream | None = None

    @classmethod
    def _class_mimetype(cls) -> str:
        """Return the Zarr MIME type string (class-level accessor)."""
        return "application/x-zarr"

    def set_uri(self, uri: str) -> None:
        """Update the store path from *uri*.

        Translates the URI to a filesystem path via ``from_uri`` and
        stores it in ``StreamSettings.store_path``.  The stream itself
        is not opened here — that happens in ``kickoff``.

        Must not be called while the writer is open.

        Parameters
        ----------
        uri : str
            New store URI (e.g. ``"file:///data/2026_02_25/scan_00001"``).
        """
        # enforces the is_open guard, stores self._uri
        super().set_uri(uri)
        self._stream_settings.store_path = from_uri(uri) + ".zarr"

    # TODO: the dimension settings should be configurable,
    # possibly from the presenter side. So the API should
    # allow the presenter to specify the dimension types and chunk sizes.
    # Maybe a per-backend dataclass with specific settings
    # that the presenter/view can populate and pass to the writer?
    def _on_prepare(self, name: str) -> None:
        """Pre-declare Zarr array dimensions for source *name*.

        Called by the base ``prepare`` after ``self._sources[name]`` is
        populated.  Builds the ``ArraySettings`` (dimensions, dtype,
        output key) that ``kickoff`` will pass to ``ZarrStream``.

        Parameters
        ----------
        name : str
            Source name just registered.
        """
        source = self._sources[name]
        height, width = source.shape

        dimensions = [
            Dimension(
                name="t",
                kind=DimensionType.TIME,
                array_size_px=source.capacity,
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

    def kickoff(self) -> None:
        """Open the Zarr stream for writing.

        The first device to call `kickoff` triggers stream creation.
        Since the stream is shared across all devices with the same store group name,
        it is a no-op for subsequent devices that call `kickoff` while the stream is already open.
        """
        if self.is_open:
            return
        super().kickoff()  # snapshots metadata, enforces URI guard, sets _is_open
        try:
            self._stream_settings.arrays = list(self._array_settings.values())
            self._stream = ZarrStream(self._stream_settings)
            if self._metadata:
                # write any additional metadata
                # before opening the stream
                flatten_md = json.dumps(self._metadata)
                self._stream.write_custom_metadata(flatten_md, overwrite=True)
        except Exception as e:
            self._is_open = False
            clear_metadata()
            raise e

    def _finalize(self) -> None:
        """Close the Zarr stream and clear per-acquisition array settings."""
        if self._stream is not None:
            self._stream.close()
            self._stream = None
        self._array_settings.clear()

    def _write_frame(self, name: str, frame: npt.NDArray[np.generic]) -> None:
        """Append *frame* to the stream under the array key for *name*."""
        if self._stream is None:
            raise RuntimeError(
                f"ZarrWriter ({self._name!r}) is not open; call kickoff() first."
            )
        self._stream.append(frame, key=name)
