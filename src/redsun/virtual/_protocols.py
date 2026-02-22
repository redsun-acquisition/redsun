from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from redsun.virtual._container import VirtualContainer


@runtime_checkable
class HasShutdown(Protocol):  # pragma: no cover
    """Protocol marking your class as capable of shutting down."""

    @abstractmethod
    def shutdown(self) -> None:
        """Shutdown an object. Performs cleanup operations."""
        ...


@runtime_checkable
class IsProvider(Protocol):  # pragma: no cover
    """Protocol marking a class as a provider of dependencies."""

    @abstractmethod
    def register_providers(self, container: VirtualContainer) -> None:
        """Register providers in the virtual container."""
        ...


@runtime_checkable
class IsInjectable(Protocol):  # pragma: no cover
    """Protocol marking a class as injectable with dependencies from the container."""

    @abstractmethod
    def inject_dependencies(self, container: VirtualContainer) -> None:
        """Inject dependencies from the container."""
        ...
