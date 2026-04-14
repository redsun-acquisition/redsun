"""Storage-level protocols for redsun.

Defines structural protocols that devices can implement to declare an
association with a storage writer, and that writers can implement to
expose optional capabilities such as metadata accumulation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from redsun.device._acquisition import DataWriter


@runtime_checkable
class HasWriterLogic(Protocol):
    """Protocol for devices that are paired with a storage writer.

    Implementing this protocol allows the storage presenter and metadata
    helper functions to discover the writer associated with a device
    automatically, without requiring explicit wiring in the application
    configuration.

    The ``writer_logic`` attribute should be populated at device construction
    time by injecting the shared [`Writer`][redsun.storage.Writer] instance.
    """

    @property
    def writer_logic(self) -> DataWriter:
        """Return the writer logic associated with this device.

        Returns
        -------
        DataWriter
            The storage writer paired with this device.  May implement the
            richer [`ControllableDataWriter`][redsun.device.ControllableDataWriter]
            interface if the backend supports multi-source writes.
        """
        ...


@runtime_checkable
class HasMetadata(Protocol):
    """Protocol for writers that accept externally-supplied metadata.

    Implemented by [`Writer`][redsun.storage.Writer] (and therefore by every
    concrete backend such as ``ZarrWriter``).  Used by helper functions and
    callbacks to forward device configuration into the active writer without
    a hard dependency on the concrete class.
    """

    def update_metadata(self, metadata: dict[str, Any]) -> None:
        """Merge *metadata* into the writer's accumulated metadata.

        Parameters
        ----------
        metadata:
            Key/value pairs to merge into the writer's metadata store.
            Existing keys are overwritten.  Values must be JSON-serialisable
            for backends that store metadata as JSON (e.g. ``ZarrWriter``).
        """
        ...

    def clear_metadata(self) -> None:
        """Remove all accumulated metadata."""
        ...


__all__ = [
    "HasMetadata",
    "HasWriterLogic",
]
