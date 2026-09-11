"""The registries a session fills for every component to read.

What the framework knows about itself, rather than what one component shares
with another: the configuration the session was built from, the devices it
made, and the bluesky document callbacks it collected. A component asks for one
by type, and the session answers.
"""

from __future__ import annotations

from ._builtins import (
    CallbackType,
    DeviceMapping,
    SessionConfig,
)

__all__ = [
    "CallbackType",
    "DeviceMapping",
    "SessionConfig",
]
