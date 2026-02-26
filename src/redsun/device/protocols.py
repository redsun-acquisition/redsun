from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from bluesky.protocols import Reading, Status


@runtime_checkable
class HasCache(Protocol):
    """Protocol for models that can cache values while inside a plan."""

    @abstractmethod
    def stash(self, values: dict[str, Reading[Any]]) -> Status:
        """Stash the readings associated with the given object name in the model cache."""
        ...

    @abstractmethod
    def clear(self) -> Status:
        """Clear the model cache."""
        ...
