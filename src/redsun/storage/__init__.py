# SPDX-License-Identifier: Apache-2.0
# The file and path providers are inspired by ophyd-async
# (https://github.com/bluesky/ophyd-async), developed by the Bluesky collaboration.
# ophyd-async is licensed under the BSD 3-Clause License.

"""Storage infrastructure for redsun devices.

- [`PathInfo`][redsun.storage.PathInfo] — storage path and configuration for one device
- [`FilenameProvider`][redsun.storage.FilenameProvider] — protocol for filename callables
- [`PathProvider`][redsun.storage.PathProvider] — protocol for path-info callables
- [`SessionPathProvider`][redsun.storage.SessionPathProvider] — structured session-scoped path provider
- [`DeviceStorageInfo`][redsun.storage.DeviceStorageInfo] — storage capability declared by a device
- [`StorageInfo`][redsun.storage.StorageInfo] — fully resolved storage location produced by the application
- [`PrepareInfo`][redsun.storage.PrepareInfo] — typed container passed to `prepare` methods
- [`HasStorage`][redsun.storage.HasStorage] — protocol for devices that declare storage capability

Devices declare storage capability by implementing `storage_info()`:

```python
from redsun.storage import DeviceStorageInfo


class MyDetector:
    def storage_info(self) -> DeviceStorageInfo:
        return DeviceStorageInfo(mimetype="application/x-zarr")
```
"""

from __future__ import annotations

from dataclasses import dataclass

from redsun.storage._path import (
    FilenameProvider,
    PathInfo,
    PathProvider,
    SessionPathProvider,
)


@dataclass
class PrepareInfo:
    """Plan-time information passed to device ``prepare()`` methods."""

    capacity: int = 0
    """Number of frames to prepare for.  ``0`` means unlimited."""

    write_forever: bool = False
    """Whether the device should prepare to write indefinitely (e.g. for live streaming)."""


__all__ = [
    # path
    "PathInfo",
    "FilenameProvider",
    "PathProvider",
    "SessionPathProvider",
    # prepare
    "DeviceStorageInfo",
    "StorageInfo",
    "PrepareInfo",
    # has storage
    "HasStorage",
]
