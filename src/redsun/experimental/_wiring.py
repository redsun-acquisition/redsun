"""Signal and slot wiring primitives, shared with the supported layer.

The wiring is the one part of the container this package did not rewrite, so
it is re-exported rather than copied. Importing it from here keeps every other
module in the package naming a single wiring module.
"""

from __future__ import annotations

from redsun.virtual._wiring import (
    SLOT_ATTR,
    SLOT_THREAD_ATTR,
    Connection,
    Ports,
    Slot,
    SlotThread,
    Subscription,
    Unconnected,
    WiringError,
    port_name,
    ports,
    slot,
)

__all__ = [
    "SLOT_ATTR",
    "SLOT_THREAD_ATTR",
    "Connection",
    "Ports",
    "Slot",
    "SlotThread",
    "Subscription",
    "Unconnected",
    "WiringError",
    "port_name",
    "ports",
    "slot",
]
