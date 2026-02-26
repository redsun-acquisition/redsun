from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from redsun.storage import Writer


@runtime_checkable
class HasWriter(Protocol):
    """Protocol for devices that have an associated writer."""

    def get_writer(self) -> Writer:
        """Get the writer associated of this device."""
        ...


__all__ = [
    "HasWriter",
]
