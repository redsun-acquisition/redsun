from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redsun.storage import DataWriter


class WriterType(StrEnum):
    ZARR = "zarr"


def create_writer(wtype: WriterType) -> DataWriter:
    """Construct a new [`DataWriter`][redsun.storage.DataWriter].

    Parameters
    ----------
    wtype : WriterType
        Writer type identifier.  See `WriterType` for supported values.

    Returns
    -------
    DataWriter
        A freshly constructed writer instance.
    """
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
