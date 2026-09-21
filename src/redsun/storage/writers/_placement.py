from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Final

from . import _acquire_zarr
from ._base import (
    WriterError,
    carries_ngff,
    root_attributes,
    sibling_uri,
    store_path,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

    from ._base import ArrayShape, Stream

ZARR: Final = "application/x-zarr"
OME_ZARR: Final = "application/x-ome-zarr"


@dataclass(frozen=True, slots=True)
class Placement:
    """Where a product goes against a store, and how a stream is opened there.

    ``streamed`` is whether frames can be appended over a run: an OME-Zarr
    store of its own is written whole, since its frame count is fixed at
    open.
    """

    path: Path
    uri: str
    streamed: bool
    open: Callable[[Mapping[str, ArrayShape]], Stream]


def placement(uri: str, mimetype: str, data_key: str) -> Placement | None:
    """Return where *data_key* goes against the store at *uri*, by *mimetype*.

    A plain Zarr store takes the product as a key. An OME-Zarr store does the
    same while its root is a plain group; a root that is an image, a plate
    or a ``bioformats2raw`` layout would lose that metadata to a new key, so
    the product becomes a store beside it, named after both. A mimetype
    neither writer knows gives ``None``.

    Raises
    ------
    WriterError
        If a plain Zarr store carries OME-Zarr metadata at its root, which
        a new key would drop.
    """
    path = store_path(uri)
    ngff_root = carries_ngff(root_attributes(path))
    match mimetype:
        case "application/x-zarr" if ngff_root:
            raise WriterError(
                f"the store at {uri} has OME-Zarr metadata at its root, which "
                f"adding a key drops; describe it as {OME_ZARR!r} to write "
                "beside it"
            )
        case "application/x-zarr":
            return Placement(
                path, uri, True, partial(_acquire_zarr.Stream, path, is_ngff=False)
            )
        case "application/x-ome-zarr" if not ngff_root:
            return Placement(
                path, uri, True, partial(_acquire_zarr.Stream, path, is_ngff=True)
            )
        case "application/x-ome-zarr":
            name = f"{path.name.split('.', 1)[0]}_{data_key}.ome.zarr"
            sibling = path.parent / name
            return Placement(
                sibling, sibling_uri(uri, name), False, partial(open_sibling, sibling)
            )
        case _:
            return None


def open_sibling(path: Path, arrays: Mapping[str, ArrayShape]) -> Stream:
    """Open an OME-Zarr store at *path*, importing its writer package on first use."""
    from ._ome_writers import Stream

    return Stream(path, arrays)
