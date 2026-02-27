"""Storage-level protocols for redsun.

Defines structural protocols that devices can implement to declare an
association with a storage writer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from redsun.storage import Writer


@runtime_checkable
class HasWriter(Protocol):
    """Protocol for devices that are paired with a storage writer.

    Implementing this protocol allows the storage presenter to discover
    the writer associated with a device automatically, without requiring
    explicit wiring in the application configuration.
    """

    def get_writer(self) -> Writer:
        """Return the writer associated with this device.

        Returns
        -------
        Writer
            The storage writer paired with this device.
        """
        ...


__all__ = [
    "HasWriter",
]
