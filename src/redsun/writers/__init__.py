"""Write a derived product against the store a run names.

`Writer` reads a run's documents for where each product goes: a key of the
acquisition's store, or a store of its own beside it. Nothing is registered
in a catalog.

Without `acquire-zarr`, importing this package raises `ImportError` naming
`redsun[zarr]`. Writing beside an OME-Zarr image needs `redsun[ome-zarr]`,
named the same way on first use.
"""

from ._base import ArrayShape, WriterError
from ._writer import Writer

__all__ = ["ArrayShape", "Writer", "WriterError"]
