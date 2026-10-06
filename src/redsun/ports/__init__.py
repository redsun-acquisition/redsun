"""The connectors a session binds between its components.

A component declares a port and names no peer; the session, the `wiring`
section of its configuration or a pairing in its `pairs` section binds one
component's signal to another's slot.
`redsun` re-exports what is here alongside the rest of the layer.
"""

from __future__ import annotations

from ._wiring import (
    ComponentNotBuilt,
    Connection,
    Link,
    Ports,
    SlotThread,
    Unconnected,
    WiringError,
    links_between,
    ports,
    slot,
)

__all__ = [
    "ComponentNotBuilt",
    "Connection",
    "Link",
    "Ports",
    "SlotThread",
    "Unconnected",
    "WiringError",
    "links_between",
    "ports",
    "slot",
]
