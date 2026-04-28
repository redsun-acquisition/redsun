from __future__ import annotations

from enum import StrEnum

from redsun.storage._base import DataWriter, SourceInfo
from redsun.storage._metadata_callback import handle_descriptor_metadata


class WriterType(StrEnum):
    """Enumeration of supported storage backends."""

    ZARR = "zarr"
    """acquire-zarr stream writer."""


def create_writer(wtype: WriterType | str) -> DataWriter:
    """Construct a new [`DataWriter`][redsun.storage.DataWriter].

    Parameters
    ----------
    wtype : WriterType | str
        Writer type identifier.  See `WriterType` for supported values.

    Returns
    -------
    DataWriter
        A freshly constructed writer instance.
    """
    wtype = WriterType(wtype)
    match wtype:
        case WriterType.ZARR:
            from redsun.storage._zarr import (
                ZarrDataWriter,
            )

            return ZarrDataWriter()
        case _:
            raise ValueError(
                f"No writer registered for type: {wtype!r}. "
                f"Supported types: {[t.value for t in WriterType]}."
            )


__all__ = [
    "WriterType",
    "DataWriter",
    "create_writer",
    "SourceInfo",
    "create_writer",
    "handle_descriptor_metadata",
]
