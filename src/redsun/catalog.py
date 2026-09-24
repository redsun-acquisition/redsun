"""Where the session's catalog is served.

Imports nothing from ``tiled``, so any component can ask, extra or not.
"""

from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["CatalogAddress"]


@dataclass(frozen=True)
class CatalogAddress:
    """Where a session's catalog is served.

    ```python
    from tiled.client import from_uri

    client = from_uri(address.uri)
    ```

    Attributes
    ----------
    uri : str
        URI of the server, with its API key. Left out of the ``repr``.
    """

    uri: str = field(repr=False)
