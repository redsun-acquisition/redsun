"""General-purpose utilities for redsun.

Exposes:
- `find_signals` — locate named signals in a `VirtualContainer`.
- `resolve_sync_or_async` — resolve a ``SyncOrAsync[T]`` value to ``T``.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import TYPE_CHECKING, TypeVar, cast

from redsun.engine import get_shared_loop

if TYPE_CHECKING:
    from collections.abc import Coroutine, Iterable
    from concurrent.futures import Future
    from typing import Any

    from psygnal import SignalInstance

    from redsun.virtual import VirtualContainer

__all__ = [
    "find_signals",
    "resolve_sync_or_async",
]


T = TypeVar("T")


def find_signals(
    container: VirtualContainer, signal_names: Iterable[str]
) -> dict[str, SignalInstance]:
    """Find signals in a `VirtualContainer` by name, regardless of owner.

    Searches all registered signal caches for each name in *signal_names*
    and returns the first match found.  Names not present in any cache are
    omitted from the result.

    This helper avoids coupling callers to the owner's instance name, which
    is assigned at runtime by the application container.

    Parameters
    ----------
    container : VirtualContainer
        The virtual container holding registered signals.
    signal_names : Iterable[str]
        Signal names to look up (e.g. ``["sigMotorMove", "sigConfigChanged"]``).

    Returns
    -------
    dict[str, SignalInstance]
        Mapping of signal name to signal instance for each name found.
        Names that are not found in any cache are omitted.
    """
    result: dict[str, SignalInstance] = {}
    remaining = set(signal_names)
    for cache in container.signals.values():
        for name in remaining & cache.keys():
            result[name] = cache[name]
        remaining -= result.keys()
        if not remaining:
            break
    return result


def resolve_sync_or_async(value: T | Coroutine[Any, Any, T]) -> T:
    """Resolve a ``SyncOrAsync[T]`` value to its concrete ``T``.

    If *value* is not a coroutine it is returned directly. If it is,
    it will submitted to the global shared event loop running
    in a background thread.

    Parameters
    ----------
    value :
        Either a plain value ``T`` or an ``Awaitable[T]``.

    Returns
    -------
    T
        The resolved value.
    """
    if inspect.iscoroutine(value):
        loop = get_shared_loop()
        future: Future[T] = asyncio.run_coroutine_threadsafe(value, loop)
        return future.result()
    return cast("T", value)
