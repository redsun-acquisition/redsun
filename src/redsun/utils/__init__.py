"""General-purpose utilities for redsun.

Exposes:
- `find_signals` — locate named signals in a `VirtualContainer`.
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
    container: VirtualContainer,
    signal_names: Iterable[str],
    owner: str | None = None,
) -> dict[str, SignalInstance]:
    """Find signals in a `VirtualContainer` by name, optionally scoped to an owner.

    The signal registry is keyed by owner first (mirroring
    ``container.signals[owner][signal]``): different components may expose
    signals with the same name, and the owner name is what discerns them.
    Pass *owner* to restrict the lookup to a single component's cache.

    When *owner* is omitted, all registered caches are searched and the
    first match per name wins — convenient when a signal name is known to
    be unique, but ambiguous otherwise. Names (or owners) not present in
    the registry are omitted from the result rather than raising.

    Parameters
    ----------
    container : VirtualContainer
        The virtual container holding registered signals.
    signal_names : Iterable[str]
        Signal names to look up (e.g. ``["sig_motor_move", "sig_config_changed"]``).
    owner : str | None
        Registry key of the owning component (its ``name``, or the alias
        used at registration). If ``None``, every cache is searched.

    Returns
    -------
    dict[str, SignalInstance]
        Mapping of signal name to signal instance for each name found.
        Names that are not found are omitted.
    """
    result: dict[str, SignalInstance] = {}
    remaining = set(signal_names)
    if owner is not None:
        cache = container.signals.get(owner, {})
        return {name: cache[name] for name in remaining & cache.keys()}
    for cache in container.signals.values():
        for name in remaining & cache.keys():
            result[name] = cache[name]
        remaining -= result.keys()
        if not remaining:
            break
    return result
