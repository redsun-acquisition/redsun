"""Module-level metadata registry for device contributions.

Non-imaging devices (motors, lights, etc.) call
[`register_metadata`][redsun.storage.metadata.register_metadata]
during their ``prepare()`` method to contribute acquisition-time metadata.
Writer backends snapshot the registry at [`Writer.kickoff`][redsun.storage.Writer.kickoff]
and clear it when the last source completes via [`Writer.complete`][redsun.storage.Writer.complete].
"""

from __future__ import annotations

import copy
from typing import Any

_registry: dict[str, dict[str, Any]] = {}


def register_metadata(name: str, metadata: dict[str, Any]) -> None:
    """Stage metadata for device *name*.

    Parameters
    ----------
    name : str
        Device name used as the registry key.
    metadata : dict[str, Any]
        JSON-serializable metadata contributed by the device.
    """
    _registry[name] = metadata


def snapshot_metadata() -> dict[str, dict[str, Any]]:
    """Return a copy of the current registry."""
    return copy.deepcopy(_registry)


def clear_metadata() -> None:
    """Clear the registry.

    Called by [`Writer.complete`][redsun.storage.Writer.complete] after the last
    source finalises, and by [`Writer.kickoff`][redsun.storage.Writer.kickoff]
    if the backend fails to open.
    """
    _registry.clear()
