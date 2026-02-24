from __future__ import annotations

from typing import TYPE_CHECKING

from redsun.storage.zarr import ZarrWriter

if TYPE_CHECKING:
    from redsun.storage._base import Writer


def make_writer(uri: str, mimetype: str = "application/x-zarr") -> "Writer":
    """Return the singleton writer for *uri* and *mimetype*.

    Delegates to :meth:`Writer.get <redsun.storage.Writer.get>` so that all
    devices sharing the same store URI receive the same backend instance.

    Parameters
    ----------
    uri : str
        Store URI (e.g. ``"file:///tmp/scan.zarr"``).
    mimetype : str
        Backend format hint. Currently only ``"application/x-zarr"`` is
        supported. Defaults to ``"application/x-zarr"``.

    Returns
    -------
    Writer
        Shared writer instance for *uri*.

    Raises
    ------
    ValueError
        If *mimetype* is not a recognised format hint.
    """
    if mimetype == "application/x-zarr":
        return ZarrWriter.get(uri)
    raise ValueError(f"Unsupported format hint: {mimetype!r}")

