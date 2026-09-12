"""How a component says what it needs and what it offers.

A component names types, never peers: a constructor parameter is a request the
session answers, and a method marked with `provides` is an answer other
components may ask for. `redsun.experimental` re-exports what is here alongside
the rest of the layer, and is the import a component is written against.
"""

from __future__ import annotations

from ._provides import provides, register_shared, shared_keys
from ._requires import (
    Devices,
    DevicesOf,
    Every,
    Maybe,
    One,
    Question,
    Requires,
    RequiresMaybe,
    RequiresOne,
    key_for,
    question_of,
    rejected,
    satisfying,
)

__all__ = [
    "Devices",
    "DevicesOf",
    "Every",
    "Maybe",
    "One",
    "Question",
    "Requires",
    "RequiresMaybe",
    "RequiresOne",
    "key_for",
    "provides",
    "question_of",
    "register_shared",
    "rejected",
    "satisfying",
    "shared_keys",
]
