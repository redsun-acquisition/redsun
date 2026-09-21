"""Writers adding a derived product to an acquisition's store.

`Writer` follows a run's documents to learn where each product goes and
writes it there, as a key of the store the acquisition wrote or as a store
of its own beside it. It registers nothing in a catalog.

Importing this package raises `ImportError` naming the extra to install when
`acquire-zarr` is missing, `redsun[zarr]`; writing beside an OME-Zarr image
needs `redsun[ome-zarr]` as well, named the same way on first use.
"""

from ._base import ArrayShape, WriterError
from ._writer import Writer

__all__ = ["ArrayShape", "Writer", "WriterError"]
