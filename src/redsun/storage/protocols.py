from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, TypeAlias, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Mapping

DeviceMetadata: TypeAlias = dict[str, Any]
"""Metadata contributed by a single device during prepare. Must be JSON-serializable."""

StorageMetadata: TypeAlias = dict[str, DeviceMetadata]
"""Metadata from all contributing devices, keyed by device name."""


@runtime_checkable
class PDeviceStorageInfo(Protocol):
    """Device-level protocol for device storage information."""

    mimetype: str
    """mimetype for the storage format."""

    extra: DeviceMetadata
    """Extra metadata contributed by the device."""


@runtime_checkable
class PStorageInfo(Protocol):
    """Application-level protocol for storage information."""

    uri: str
    """URI to the storage location."""

    devices: Mapping[str, PDeviceStorageInfo]
    """Information about the devices that contributed to the storage information."""
