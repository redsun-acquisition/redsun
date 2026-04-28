from __future__ import annotations

from typing import TYPE_CHECKING

from redsun.storage.protocols import HasWriterLogic

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Any

    from redsun.storage._base import DataWriter


def get_available_writers(
    devices: Mapping[str, Any],
) -> dict[str, dict[str, DataWriter]]:
    """Return writers grouped by mimetype, discovered from *devices*.

    Iterates over every device in *devices* and collects the unique
    [`DataWriter`][redsun.storage.DataWriter] instances
    exposed via the [`HasWriterLogic`][redsun.storage.HasWriterLogic] protocol,
    grouped for convenient iteration by format.  The outer key is the mimetype
    string (e.g. ``"application/x-zarr"``); the inner key is the writer's
    class name.

    Parameters
    ----------
    devices :
        Mapping of device name to device object — typically the
        application's full device registry.

    Returns
    -------
    dict[str, dict[str, DataWriter]]
        ``{mimetype: {writer_class_name: writer}}``
    """
    seen_ids: set[int] = set()
    result: dict[str, dict[str, DataWriter]] = {}
    for device in devices.values():
        if isinstance(device, HasWriterLogic):
            writer = device.writer
            seen_ids.add(id(writer))
            result.setdefault(writer.mimetype, {})[type(writer).__name__] = writer
    return result
