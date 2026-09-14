"""General-purpose utilities.

Exposes:
- `find_signals` - locate named signals in a `VirtualContainer`.
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

    The registry is keyed by owner first (``container.signals[owner][signal]``),
    since components may share signal names. *owner* limits the search to one
    component; without it every owner is searched and the first match per name
    wins. Names not found are left out.

    Parameters
    ----------
    container : VirtualContainer
        The virtual container holding registered signals.
    signal_names : Iterable[str]
        Signal names to look up (e.g. ``["sig_motor_move", "sig_config_changed"]``).
    owner : str | None
        Registry key of the owning component: its ``name``, or the alias
        given at registration. ``None`` searches every owner.

    Returns
    -------
    dict[str, SignalInstance]
        Signal instance by name, for each name found.
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
