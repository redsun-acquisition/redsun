from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class HasAsyncShutdown(Protocol):
    """Protocol for devices that support asynchronous shutdown."""

    async def shutdown(self) -> None:
        """Asynchronously shutdown the device."""
        ...
