"""Writers adding a derived product to a store an acquisition already wrote.

One module per format, each with a `write` function taking the fields of the
`StreamResource` document the product is derived from. A writer chooses where
the product lands by reading the store it is given, and returns its URI.

A writer registers nothing. Whether a product also belongs in a catalog is the
caller's decision, made per product.
"""

from redsun.storage.writers._base import WriterError

__all__ = ["WriterError"]
