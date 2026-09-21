"""Write a derived product into a plain Zarr store.

This module is not the `zarr` package; absolute imports keep them apart.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._acquire_zarr import Stream
from ._base import (
    ArrayShape,
    WriterError,
    carries_ngff,
    merge_attributes,
    root_attributes,
    store_path,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from numpy.typing import NDArray

__all__ = ["write"]


def frame_layout(data: NDArray[Any]) -> ArrayShape:
    """Return the layout of one frame of *data*: itself when 2D, else its slices."""
    return ArrayShape.of(data.shape if data.ndim == 2 else data.shape[1:], data.dtype)


def write(
    uri: str,
    *,
    data_key: str,
    data: NDArray[Any],
    metadata: Mapping[str, Any] | None = None,
) -> str:
    """Add *data* as *data_key* to the store at *uri*, and return *uri*.

    *metadata* goes to the new key's own group.

    Raises
    ------
    WriterError
        If the root carries OME-Zarr metadata, which a new key would drop (use
        `ome_zarr`), or the array has too few or too many dimensions.
    """
    path = store_path(uri)
    if carries_ngff(root_attributes(path)):
        raise WriterError(
            f"the store at {uri} has OME-Zarr metadata at its root, which "
            "adding a key drops; write it with redsun.storage.writers."
            "ome_zarr instead"
        )
    stream = Stream(path, {data_key: frame_layout(data)}, is_ngff=False)
    try:
        stream.append(data_key, data)
    finally:
        stream.close()
    if metadata:
        merge_attributes(path / data_key, metadata)
    return uri
