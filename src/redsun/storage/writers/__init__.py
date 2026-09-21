"""Writers adding a derived product to an acquisition's store.

One module per format, each with a `write` taking the fields of the
`StreamResource` document. A writer reads the store, decides where the product
goes and returns its URI. It registers nothing in a catalog.

Importing a writer module raises `ImportError` naming the extra to install
when its package is missing: `redsun[zarr]` for `zarr`, `redsun[ome-zarr]`
for `ome_zarr`.
"""

from ._base import WriterError

__all__ = ["WriterError"]
