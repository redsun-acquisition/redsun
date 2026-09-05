"""The connectors a session binds between its components.

A component declares a port and names no peer; the session, or the ``wiring``
section of its configuration, binds one component's signal to another's slot.
`redsun.experimental` re-exports what is here alongside the rest of the layer.
"""

from __future__ import annotations

from ._wiring import (
    ComponentNotBuilt,
    Connection,
    SessionNotBuilt,
    WiringError,
    slot,
)

__all__ = [
    "ComponentNotBuilt",
    "Connection",
    "SessionNotBuilt",
    "WiringError",
    "slot",
]
