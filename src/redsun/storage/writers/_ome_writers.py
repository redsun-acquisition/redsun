from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._base import WriterError, axis_names

try:
    import ome_writers as ow
except ImportError as error:
    raise ImportError(
        "ome-writers is needed to write an OME-Zarr product and is not "
        "installed; install it with 'pip install redsun[ome-zarr]'"
    ) from error

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from numpy.typing import NDArray

    from ._base import ArrayShape


class Stream:
    """An OME-Zarr store of its own, holding one image.

    The layout is the whole image, not one frame: `ome-writers` allocates
    every frame at open, so the stream is closed once that many were
    appended.
    """

    __slots__ = ("_data_key", "_layout", "_path", "_stream")

    def __init__(self, path: Path, arrays: Mapping[str, ArrayShape]) -> None:
        if len(arrays) != 1:
            raise WriterError(
                f"an OME-Zarr store holds one image; {sorted(arrays)} were "
                f"asked for at {path}"
            )
        ((self._data_key, self._layout),) = arrays.items()
        self._path = path
        settings = ow.AcquisitionSettings(
            root_path=str(path),
            dimensions=tuple(
                ow.dims_from_standard_axes(
                    dict(
                        zip(
                            axis_names(len(self._layout.shape)),
                            self._layout.shape,
                            strict=True,
                        )
                    )
                )
            ),
            dtype=str(self._layout.dtype),
            format=ow.OmeZarrFormat(backend="acquire-zarr"),
        )
        self._stream = ow.create_stream(settings)

    def append(self, data_key: str, data: NDArray[Any]) -> None:
        """Append the 2D frames of *data*, in order, to the image.

        Raises
        ------
        WriterError
            If *data_key* is not the image, or *data* does not match its
            layout.
        """
        if data_key != self._data_key:
            raise WriterError(
                f"{data_key!r} is not the image of the store at {self._path}, "
                f"which holds {self._data_key!r}"
            )
        frames = self._layout.check(data_key, data).reshape(-1, *data.shape[-2:])
        for frame in frames:
            self._stream.append(frame)

    def node(self, data_key: str) -> Path:
        """Return the store's root, which is the image."""
        return self._path

    def close(self) -> None:
        """Finish the image; nothing can be appended afterwards."""
        self._stream.close()
