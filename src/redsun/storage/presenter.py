from __future__ import annotations

from redsun.storage._base import Writer


def get_available_writers() -> dict[str, dict[str, Writer]]:
    """Return all registered writers grouped by mimetype.

    Provides a presenter with a view of the current writer
    registry, grouped for convenient iteration by format.  The outer
    key is the mimetype string (e.g. ``"application/x-zarr"``); the
    inner key is the store group name (e.g. ``"default"``).

    Returns
    -------
    dict[str, dict[str, Writer]]
        ``{mimetype: {group_name: writer}}``
    """
    result: dict[str, dict[str, Writer]] = {}
    with Writer._registry_lock:
        for (name, mimetype), writer in Writer._registry.items():
            result.setdefault(mimetype, {})[name] = writer
    return result
