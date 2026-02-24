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
    """Per-device storage information."""

    mimetype: str = field(default="")
    """`mimetype` hint for the storage format."""

    extra: DeviceMetadata = field(default_factory=dict)
    """Extra metadata contributed by the device."""


@dataclass
class StorageInfo(PStorageInfo):
    """Per-application storage information."""

    uri: str = field(default="")
    """URI to the storage location."""

    devices: dict[str, DeviceStorageInfo] = field(default_factory=dict)
    """Information about the devices contributing to storage, keyed by device name."""


@dataclass
class PrepareInfo:
    """Information to be passed as value to `prepare` methods.

    !!! note

        Currently holds only one field, `storage`. The goal is
        to experiment to find the right set of information
        to pass to `prepare` methods in the future
        (i.e. trigger information).

    """

    storage: StorageInfo = field(default_factory=StorageInfo)
    """Application-level storage information."""


@runtime_checkable
class HasStorage(HasName, Protocol):
    """Protocol for objects that have storage information."""

    def storage_info(self) -> DeviceStorageInfo:
        """Return storage information for this device."""
