"""Write a derived product into a plain Zarr store.

`zarr` here is this module, not the `zarr` package: imports resolve absolutely,
so the reader is the only one who has to tell them apart.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from redsun.storage.writers._acquire_zarr import append_key
from redsun.storage.writers._base import (
    WriterError,
    merge_attributes,
    root_attributes,
    store_path,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from numpy.typing import NDArray

__all__ = ["write"]


def write(
    uri: str,
    *,
    data_key: str,
    data: NDArray[Any],
    metadata: Mapping[str, Any] | None = None,
) -> str:
    """Write *data* as *data_key* into the store at *uri*, and return its URI.

    The key is added to the store in place, so the returned URI is *uri*.
    *metadata* is written to the new key's own group.

    Raises
    ------
    WriterError
        If the store's root is an OME-Zarr image, since adding a key to one
        drops the root's `ome` block and the image stops being OME-Zarr; use
        the `ome_zarr` module for those. Also if `acquire-zarr` is not
        installed, or the array has too few or too many dimensions.
    """
    path = store_path(uri)
    attributes = root_attributes(path)
    if "ome" in attributes or "multiscales" in attributes:
        raise WriterError(
            f"the store at {uri} is an OME-Zarr image, and adding a key to one "
            "drops its root metadata; write it with redsun.storage.writers."
            "ome_zarr instead"
        )
    append_key(path, data_key=data_key, data=data, is_ngff=False)
    if metadata:
        merge_attributes(path / data_key, metadata)
    return uri
