"""General-purpose utilities for redsun.

Currently exposes `find_signals`, a helper for locating named signals
in a `VirtualContainer` without needing to know the owner's instance name.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from psygnal import SignalInstance

    from redsun.virtual import VirtualContainer

__all__ = [
    "find_signals",
]


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
