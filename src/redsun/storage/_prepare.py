from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from bluesky.protocols import HasName

from redsun.storage.protocols import (
    DeviceMetadata,
    PDeviceStorageInfo,
    PStorageInfo,
)


@dataclass
class DeviceStorageInfo(PDeviceStorageInfo):
    """Concrete implementation of PDeviceStorageInfo."""

    format_hint: str
    """`mimetype` hint for the storage format."""

    extra: DeviceMetadata = field(default_factory=dict)
    """Extra metadata contributed by the device."""


@dataclass
class StorageInfo(PStorageInfo):
    """Application-resolved storage information with information from contributing devices."""

    uri: str
    """URI to the storage location."""

    devices: dict[str, DeviceStorageInfo] = field(default_factory=dict)
    """Information about the devices that contributed to the storage information, keyed by device name."""


@dataclass
class PrepareInfo:
    """Information to be passed as value to `prepare` methods."""

    storage: StorageInfo | None = None
    """Storage information, if any, from previous devices in the prepare sequence."""


@runtime_checkable
class HasStorage(HasName, Protocol):
    """Protocol for objects that have storage information."""

    def storage_info(self) -> DeviceStorageInfo:
        """Return storage information for this device."""
