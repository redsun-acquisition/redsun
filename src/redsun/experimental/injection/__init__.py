"""How a component says what it needs and what it offers.

A component names types, never peers: a constructor parameter is a request the
session answers, and a method marked with `provides` is an answer other
components may ask for. `redsun.experimental` re-exports what is here alongside
the rest of the layer, and is the import a component is written against.
"""

from __future__ import annotations

from ._provides import provides
from ._requires import DevicesOf, Requires, RequiresMaybe, RequiresOne, Satisfying

__all__ = [
    "DevicesOf",
    "Requires",
    "RequiresMaybe",
    "RequiresOne",
    "Satisfying",
    "provides",
]
