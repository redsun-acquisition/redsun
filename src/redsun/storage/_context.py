from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from redsun.storage._prepare import StorageInfo

if TYPE_CHECKING:
    from redsun.storage._path import PathInfo, PathProvider
    from redsun.storage._prepare import HasStorage
    from redsun.storage.protocols import DeviceMetadata


@dataclass
class StorageContext:
    name: str
    path_provider: PathProvider
    extra: DeviceMetadata = field(default_factory=dict)

    def resolve(self, device: HasStorage) -> StorageInfo:
        """Merge the device's declared capability with an application-resolved URI.

        The returned StorageInfo.devices is pre-seeded with the device's own
        DeviceStorageInfo entry. Motors and lights will add their own entries
        during their prepare() calls.
        """
        path_info: PathInfo = self.path_provider(device.name)
        device_info = device.storage_info()
        return StorageInfo(
            uri=path_info.store_uri,
            devices={device.name: device_info},
        )
