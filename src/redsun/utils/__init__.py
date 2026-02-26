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
    """Find signals in the virtual container by name, regardless of owner.

    Searches all registered signal caches for each name in
    ``signal_names``, returning a mapping of signal name to instance.
    Names not found in any cache are omitted from the result. This
    avoids coupling to the owner's instance name, which is set at
    runtime by the application container.

    Parameters
    ----------
    container :
        The virtual container holding registered signals.
    signal_names :
        The signal names to look for (e.g. ``["sigMotorMove", "sigConfigChanged"]``).

    Returns
    -------
    dict[str, SignalInstance]
        Mapping of signal name to signal instance for each name found.
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
