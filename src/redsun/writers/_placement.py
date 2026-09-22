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
    """Where a product goes, and how to open a stream there.

    ``streamed`` is false for an OME-Zarr store of its own: its frame count
    is fixed at open, so it is written whole.
    """

    path: Path
    uri: str
    streamed: bool
    open_stream: Callable[[Mapping[str, ArrayShape]], Stream]


def placement(uri: str, mimetype: str, data_key: str) -> Placement | None:
    """Return where *data_key* goes against the store at *uri*, or ``None`` for an unknown *mimetype*.

    A plain root takes the product as a key. A root carrying OME-Zarr
    metadata (an image, a plate, a ``bioformats2raw`` layout) would lose it
    to a new key, so the product becomes a store beside it, named after both.

    Raises
    ------
    WriterError
        If a store described as plain Zarr carries OME-Zarr metadata at its
        root.
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
    """Open an OME-Zarr store at *path*; its package is imported here, on first use."""
    from ._ome_writers import Stream

    return Stream(path, arrays)
