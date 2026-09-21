"""Write a derived product against an OME-Zarr store.

A root that is a plain group takes the product as another key. A root carrying
OME-Zarr metadata would lose its `ome` block to a new key, so the product is
written as a store of its own beside it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from . import _ome_writers
from ._acquire_zarr import Stream
from ._base import (
    ArrayShape,
    carries_ngff,
    merge_attributes,
    root_attributes,
    sibling_uri,
    store_path,
)
from .zarr import frame_layout

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from numpy.typing import NDArray

__all__ = ["write"]


def write(
    uri: str,
    *,
    data_key: str,
    data: NDArray[Any],
    metadata: Mapping[str, Any] | None = None,
) -> str:
    """Write *data* for *data_key* against the store at *uri*, and return its URI.

    That is *uri* when the product joined the store, and the new store's when
    it went beside it.

    Raises
    ------
    WriterError
        If the array has too few or too many dimensions.
    """
    path = store_path(uri)
    if carries_ngff(root_attributes(path)):
        return _write_sibling(
            uri, path, data_key=data_key, data=data, metadata=metadata
        )
    stream = Stream(path, {data_key: frame_layout(data)}, is_ngff=True)
    try:
        stream.append(data_key, data)
    finally:
        stream.close()
    if metadata:
        merge_attributes(path / data_key, metadata)
    return uri


def _write_sibling(
    uri: str,
    path: Path,
    *,
    data_key: str,
    data: NDArray[Any],
    metadata: Mapping[str, Any] | None,
) -> str:
    """Write *data* as an OME-Zarr store of its own, beside the one at *path*."""
    name = f"{path.name.split('.', 1)[0]}_{data_key}.ome.zarr"

    stream = _ome_writers.Stream(
        path.parent / name, {data_key: ArrayShape.of(data.shape, data.dtype)}
    )
    try:
        stream.append(data_key, data)
    finally:
        stream.close()
    if metadata:
        merge_attributes(path.parent / name, {"redsun": dict(metadata)})
    return sibling_uri(uri, name)
