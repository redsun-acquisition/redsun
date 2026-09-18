"""Where the session's catalog of runs is served, as components ask for it.

Importing this module imports nothing from ``tiled``, so a component can ask
for the catalog whether or not the ``tiled`` extra is installed.
"""

from __future__ import annotations

from dataclasses import dataclass

import dependency_injector.providers as dip

__all__ = ["CATALOG", "CatalogAddress"]


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
        URI of the server, carrying its API key, so a client needs nothing
        else to connect.
    """

    uri: str


CATALOG: dip.Dependency[CatalogAddress] = dip.Dependency(instance_of=CatalogAddress)
"""Key for the session's catalog address, bound by the container when the
session has a ``tiled`` section."""
