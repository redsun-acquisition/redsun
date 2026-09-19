from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from ._container import VirtualContainer


@runtime_checkable
class HasShutdown(Protocol):  # pragma: no cover
    """A class that shuts down synchronously."""

    @abstractmethod
    def shutdown(self) -> None:
        """Clean up. Called on presenters and container hooks."""
        ...


@runtime_checkable
class IsProvider(Protocol):  # pragma: no cover
    """A class providing dependencies to the virtual container."""

    @abstractmethod
    def register_providers(self, container: VirtualContainer) -> None:
        """Register providers in the virtual container."""
        ...


@runtime_checkable
class IsInjectable(Protocol):  # pragma: no cover
    """A class receiving dependencies from the virtual container."""

    @abstractmethod
    def inject_dependencies(self, container: VirtualContainer) -> None:
        """Inject dependencies from the container."""
        ...
