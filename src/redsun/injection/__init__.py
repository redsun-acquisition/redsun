"""How a component says what it needs and what it offers.

A component names types, never peers: a constructor parameter is a request the
session answers, and a method marked with `provides` is an answer other
components may ask for. `redsun` re-exports `DevicesOf`, `provides`, `rejected`
and `satisfying`, which are the imports a component is written against.
`Registry` is the table the session builds components out of, and is not
re-exported.
"""

from __future__ import annotations

from ._census import DevicesOf, rejected, satisfying
from ._provides import provides
from ._registry import Registry

__all__ = ["DevicesOf", "Registry", "provides", "rejected", "satisfying"]
