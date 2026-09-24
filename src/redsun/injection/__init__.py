"""How a component says what it needs and what it offers.

A component names types, never peers: a constructor parameter is a request the
session answers, and a method marked with `provides` is an answer other
components may ask for. `redsun` re-exports what is here alongside
the rest of the layer, and is the import a component is written against.
"""

from __future__ import annotations

from ._census import Devices, DevicesOf, devices_protocol, rejected, satisfying
from ._provides import constant, provides, register_shared, shared_keys

__all__ = [
    "Devices",
    "DevicesOf",
    "constant",
    "devices_protocol",
    "provides",
    "register_shared",
    "rejected",
    "satisfying",
    "shared_keys",
]
