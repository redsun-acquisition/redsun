"""Writers adding a derived product to an acquisition's store.

One module per format, each with a `write` taking the fields of the
`StreamResource` document. A writer reads the store, decides where the product
goes and returns its URI. It registers nothing in a catalog.
"""

from ._base import WriterError

__all__ = ["WriterError"]
