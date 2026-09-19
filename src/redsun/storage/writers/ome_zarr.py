"""Write a derived product against an OME-Zarr store.

A root that is a plain group takes the product as another key. A root carrying
OME-Zarr metadata would lose its `ome` block to a new key, so the product is
written as a store of its own beside it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._acquire_zarr import append_key
from ._base import (
    axis_names,
    carries_ngff,
    merge_attributes,
    require,
    root_attributes,
    sibling_uri,
    store_path,
)

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
        If the package the store needs is not installed, or the array has too
        few or too many dimensions.
    """
    path = store_path(uri)
    if carries_ngff(root_attributes(path)):
        return _write_sibling(
            uri, path, data_key=data_key, data=data, metadata=metadata
        )
    append_key(path, data_key=data_key, data=data, is_ngff=True)
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
    ow = require("ome_writers", extra="zarr")
    name = f"{path.name.split('.', 1)[0]}_{data_key}.ome.zarr"

    settings = ow.AcquisitionSettings(
        root_path=str(path.parent / name),
        dimensions=ow.dims_from_standard_axes(
            dict(zip(axis_names(data.ndim), data.shape, strict=True))
        ),
        dtype=str(data.dtype),
        format=ow.OmeZarrFormat(backend="acquire-zarr"),
    )
    with ow.create_stream(settings) as stream:
        for frame in data.reshape(-1, *data.shape[-2:]):
            stream.append(frame)
        if metadata:
            stream.set_global_metadata("redsun", dict(metadata))
    return sibling_uri(uri, name)
