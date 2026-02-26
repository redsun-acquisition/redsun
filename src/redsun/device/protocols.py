"""Device-level protocols for redsun.

This module defines structural protocols that devices can implement to
participate in specific redsun behaviours, beyond the standard Bluesky
device protocols.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from bluesky.protocols import Reading, Status


@runtime_checkable
class HasCache(Protocol):
    """Protocol for devices that can cache readings during a plan.

    Devices implementing this protocol can accumulate readings in an
    internal cache (e.g. for metadata collection or deferred writing)
    and have that cache cleared between acquisitions.
    """

    @abstractmethod
    def stash(self, values: dict[str, Reading[Any]]) -> Status:
        """Stash *values* into the device cache.

        Parameters
        ----------
        values : dict[str, Reading[Any]]
            Readings to cache, keyed by the canonical ``name-property``
            key returned by ``describe()``.

        Returns
        -------
        Status
            A status object that completes when the cache operation finishes.
        """
        ...

    @abstractmethod
    def clear(self) -> Status:
        """Clear all cached readings.

        Returns
        -------
        Status
            A status object that completes when the cache is empty.
        """
        ...
