from __future__ import annotations

from typing import TYPE_CHECKING

from redsun.storage._zarr import ZarrWriter

if TYPE_CHECKING:
    from redsun.storage._base import Writer


def make_writer(
    mimetype: str,
    name: str = "default",
) -> Writer:
    """Return the singleton writer for *(name, mimetype)*.

    Delegates to the appropriate
    [Writer.get][redsun.storage.Writer.get], depending on *mimetype*,
    so that all devices get the same writer instance for the same *(name, mimetype)*.

    Parameters
    ----------
    mimetype : str
        Backend format.  Currently only ``"application/x-zarr"`` is
        supported.
    name : str
        Store group name.  All devices that should write into the same
        physical store must use the same name.  Defaults to
        ``"default"``, which is correct for the common single-store
        case.

    Returns
    -------
    Writer
        Singleton writer instance for *(name, mimetype)*.

    Raises
    ------
    ValueError
        If *mimetype* is not a recognised format.
    """
    try:
        if mimetype == "application/x-zarr":
            return ZarrWriter.get(name)
        raise ValueError(f"Unsupported mimetype: {mimetype!r}")
    except ImportError as e:
        raise ValueError(f"Cannot create writer for mimetype {mimetype!r}") from e
