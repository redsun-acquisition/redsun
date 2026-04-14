from __future__ import annotations

from typing import TYPE_CHECKING

from redsun.storage._base import Writer
from redsun.storage.protocols import HasWriterLogic

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Any


def get_available_writers(
    devices: Mapping[str, Any],
) -> dict[str, dict[str, Writer]]:
    """Return writers grouped by mimetype, discovered from *devices*.

    Iterates over every device in *devices* and collects the unique
    :class:`Writer` instances exposed via the
    :class:`~redsun.storage.HasWriterLogic` protocol, grouped for convenient
    iteration by format.  The outer key is the mimetype string
    (e.g. ``"application/x-zarr"``); the inner key is the store group
    name (e.g. ``"default"``).

    Parameters
    ----------
    devices :
        Mapping of device name to device object — typically the
        application's full device registry.

    Returns
    -------
    dict[str, dict[str, Writer]]
        ``{mimetype: {group_name: writer}}``
    """
    seen_ids: set[int] = set()
    result: dict[str, dict[str, Writer]] = {}
    for device in devices.values():
        if isinstance(device, HasWriterLogic):
            writer = device.writer_logic
            if isinstance(writer, Writer) and id(writer) not in seen_ids:
                seen_ids.add(id(writer))
                result.setdefault(writer.mimetype, {})[writer._name] = writer
    return result
