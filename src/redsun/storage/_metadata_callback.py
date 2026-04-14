"""Helper for propagating descriptor configuration into active writers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from redsun.storage.protocols import HasMetadata, HasWriterLogic

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Any

    from event_model.documents import EventDescriptor


def handle_descriptor_metadata(
    doc: EventDescriptor,
    devices: Mapping[str, Any],
) -> None:
    """Forward descriptor configuration snapshots into associated writers.

    Intended to be called from within a bluesky callback's ``descriptor``
    handler.  For each device name found in the descriptor's
    ``configuration`` section, the function checks whether the
    corresponding device implements :class:`~redsun.storage.HasWriterLogic`
    and whether its writer implements :class:`~redsun.storage.HasMetadata`.
    When both conditions hold, the configuration snapshot is forwarded to
    the writer via :meth:`~redsun.storage.HasMetadata.set_metadata`.

    Because bluesky emits one descriptor per stream name per run, this
    function will typically be called once per run.  The writer accumulates
    all metadata set through this path and applies it on each subsequent
    :meth:`~redsun.storage.Writer.open` call; the accumulated metadata is
    cleared on :meth:`~redsun.storage.Writer.close` so the next run starts
    with a clean slate.

    Parameters
    ----------
    doc:
        The bluesky ``EventDescriptor`` document as received by a callback.
    devices:
        Mapping of device name to device object — typically the
        application's full device registry.

    Examples
    --------
    Embed in a custom callback::

        class MyCallback:
            def __init__(self, devices):
                self._devices = devices

            def descriptor(self, doc):
                handle_descriptor_metadata(doc, self._devices)
                # ... rest of callback logic
    """
    config: dict[str, Any] = doc.get("configuration", {})
    for device_name, device_config in config.items():
        device = devices.get(device_name)
        if device is None or not isinstance(device, HasWriterLogic):
            continue
        writer = device.writer_logic
        if isinstance(writer, HasMetadata):
            writer.update_metadata({device_name: device_config})
