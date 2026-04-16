"""Storage-level protocols for redsun.

Defines structural protocols that devices can implement to declare an
association with a storage writer, and that writers can implement to
expose optional capabilities such as metadata accumulation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from redsun.storage import DataWriter


@runtime_checkable
class HasWriterLogic(Protocol):
    """Protocol for devices that are paired with a storage writer.

    Implementing this protocol allows the storage presenter and metadata
    helper functions to discover the writer associated with a device
    automatically, without requiring explicit wiring in the application
    configuration.

    The ``writer_logic`` attribute should be populated at device construction
    time by injecting the shared
    [`DataWriter`][redsun.storage.DataWriter] instance.
    """

    @property
    def writer_logic(self) -> DataWriter | None:
        """Return the writer logic associated with this device, or ``None``.

        ``None`` indicates the writer has not yet been injected (e.g. in
        headless or test scenarios).  Callers should check for ``None``
        before using the writer.

        Returns
        -------
        DataWriter | None
            The storage writer paired with this device, or ``None``.
        """
        ...


@runtime_checkable
class HasMetadata(Protocol):
    """Protocol for writers that accept externally-supplied metadata.

    Implemented by [`DataWriter`][redsun.storage.DataWriter]
    (and therefore by every concrete backend such as ``ZarrDataWriter``).  Used by
    helper functions and callbacks to forward device configuration into the
    active writer without a hard dependency on the concrete class.
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
