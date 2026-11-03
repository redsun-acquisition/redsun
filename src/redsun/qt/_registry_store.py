"""The injection store of the session's application, answering from its registry.

`app-model` fills a command's parameters through the store of its application,
and nothing is ever registered on it: once a registry is set, every lookup goes
to the registry.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from in_n_out import Store

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from ..injection import Registry

T = TypeVar("T")


class RegistryStore(Store):
    """A store answering from `registry`, once one is set."""

    registry: Registry | None = None
    """The registry answering every lookup; `None` leaves the store as it is."""

    def iter_providers(
        self, type_hint: type[T] | object
    ) -> Iterator[Callable[[], T | None]]:
        """Yield the providers of *type_hint* held by `registry`."""
        if self.registry is None:
            return super().iter_providers(type_hint)
        return self.registry.providers(type_hint)  # type: ignore[return-value]
