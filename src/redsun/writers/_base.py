from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Protocol
from urllib.parse import urlparse
from urllib.request import url2pathname

import numpy as np

if TYPE_CHECKING:
    from collections.abc import Mapping

    from numpy.typing import DTypeLike, NDArray

__all__ = ["ArrayShape", "Stream", "WriterError"]

_AXIS_NAMES: Final = ("t", "c", "z", "y", "x")


class WriterError(RuntimeError):
    """Raised when a product cannot be written against a store."""


@dataclass(frozen=True, slots=True)
class ArrayShape:
    """Shape and dtype of one frame; a stream appends frames along a leading axis."""

    shape: tuple[int, ...]
    dtype: np.dtype[Any]

    @classmethod
    def of(cls, shape: tuple[int, ...], dtype: DTypeLike) -> ArrayShape:
        """Return the layout with *shape* and *dtype* normalised."""
        return cls(tuple(int(size) for size in shape), np.dtype(dtype))

    def check(self, data_key: str, data: NDArray[Any]) -> NDArray[Any]:
        """Return *data* contiguous, as one frame or a stack of frames of this layout.

        Raises
        ------
        WriterError
            If the trailing dimensions or the dtype differ from this layout.
        """
        if data.dtype != self.dtype:
            raise WriterError(
                f"{data_key!r} was declared as {self.dtype.name}; "
                f"an array of {data.dtype.name} cannot be appended to it"
            )
        if data.ndim < len(self.shape) or data.shape[-len(self.shape) :] != self.shape:
            raise WriterError(
                f"{data_key!r} was declared with frames of shape {self.shape}; "
                f"an array of shape {data.shape} cannot be appended to it"
            )
        return np.ascontiguousarray(data)


class Stream(Protocol):
    """A store open for appending to the arrays declared at open."""

    def append(self, data_key: str, data: NDArray[Any]) -> None:
        """Append one frame, or a stack of frames, to *data_key*."""

    def node(self, data_key: str) -> Path:
        """Return the group holding *data_key*."""

    def close(self) -> None:
        """Finish every array; no append afterwards."""


def store_path(uri: str) -> Path:
    """Return the local path of a `file://` store URI."""
    parsed = urlparse(uri)
    if parsed.scheme != "file":
        raise WriterError(
            f"{uri!r} is not a file:// URI; only local stores are written"
        )
    return Path(url2pathname(parsed.path))


def sibling_uri(uri: str, name: str) -> str:
    """Return the URI of *name* beside the store *uri* names."""
    return f"{uri.rstrip('/').rsplit('/', 1)[0]}/{name}"


def root_attributes(path: Path) -> Mapping[str, Any]:
    """Return the attributes of a Zarr store's root group, empty when it has none.

    Reads the metadata file directly, so neither `zarr` nor a reader package
    is needed to tell a root carrying NGFF metadata from a plain group.
    """
    v3 = path / "zarr.json"
    if v3.is_file():
        document: dict[str, Any] = json.loads(v3.read_text(encoding="utf-8"))
        attributes: dict[str, Any] = document.get("attributes", {})
        return attributes
    v2 = path / ".zattrs"
    if v2.is_file():
        zattrs: dict[str, Any] = json.loads(v2.read_text(encoding="utf-8"))
        return zattrs
    return {}


def carries_ngff(attributes: Mapping[str, Any]) -> bool:
    """Return whether *attributes* hold NGFF metadata of their own.

    An image, a plate or a ``bioformats2raw`` layout all do. Adding a key to
    such a group drops that metadata.
    """
    return "ome" in attributes or "multiscales" in attributes


def merge_attributes(path: Path, metadata: Mapping[str, Any]) -> None:
    """Merge *metadata* into the attributes of the group at *path*.

    The group is the product's own, never the store's root: a stream closing
    on the store rewrites the root's metadata and would drop it.
    """
    node = path / "zarr.json"
    document = json.loads(node.read_text(encoding="utf-8"))
    document.setdefault("attributes", {}).update(metadata)
    node.write_text(json.dumps(document, indent=2), encoding="utf-8")


def axis_names(ndim: int) -> tuple[str, ...]:
    """Return NGFF axis names for an array of *ndim* dimensions.

    Names are taken from the end of `t, c, z, y, x`, the order NGFF requires.
    """
    if not 2 <= ndim <= len(_AXIS_NAMES):
        raise WriterError(
            f"an array of {ndim} dimensions cannot be written; "
            f"between 2 and {len(_AXIS_NAMES)} are supported"
        )
    return _AXIS_NAMES[-ndim:]
