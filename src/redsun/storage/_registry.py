from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ._base import BaseStorage

__all__ = [
    "clear_registry",
    "get_storage",
    "register_storage",
    "reset_group",
]

_REGISTRY: dict[tuple[str, str], BaseStorage] = {}


def register_storage(group: str, storage: BaseStorage) -> None:
    """Register a storage instance under ``(group, storage.mimetype)``.

    Raises
    ------
    KeyError
        If a storage is already registered under that key.
    """
    key = (group, storage.mimetype)
    if key in _REGISTRY:
        raise KeyError(f"A storage is already registered for {key!r}.")
    _REGISTRY[key] = storage


def get_storage(group: str, mimetype: str) -> BaseStorage:
    """Resolve the storage instance for ``(group, mimetype)``.

    Raises
    ------
    KeyError
        If no storage is registered under that key.
    """
    try:
        return _REGISTRY[(group, mimetype)]
    except KeyError:
        raise KeyError(
            f"No storage registered for group {group!r} with mimetype {mimetype!r}."
        ) from None


async def reset_group(group: str) -> None:
    """Abort every storage in `group`, dropping queued frames.

    Instances stay registered, so a session's storage outlives one burst.
    """
    for (candidate, _), storage in list(_REGISTRY.items()):
        if candidate == group:
            await storage.close(flush=False)


def clear_registry() -> None:
    """Remove every registered storage, for session teardown and tests.

    Removed storages are not closed, so an open one leaks its store. Call
    `reset_group`, or `close` each storage, first if one may be open.
    """
    _REGISTRY.clear()
