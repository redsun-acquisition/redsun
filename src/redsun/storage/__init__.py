# SPDX-License-Identifier: Apache-2.0
# The file and path providers are inspired by ophyd-async
# (https://github.com/bluesky/ophyd-async), developed by the Bluesky collaboration.
# ophyd-async is licensed under the BSD 3-Clause License.

"""Storage infrastructure for redsun devices.

This subpackage provides the primitives for storage:

- [`Writer`][redsun.storage.Writer] — abstract base class for storage backends
- [`FrameSink`][redsun.storage.FrameSink] — device-facing handle for pushing frames
- [`SourceInfo`][redsun.storage.SourceInfo] — per-source runtime acquisition state
- [`PathInfo`][redsun.storage.PathInfo] — storage path and configuration for one device
- [`FilenameProvider`][redsun.storage.FilenameProvider] — protocol for filename callables
- [`PathProvider`][redsun.storage.PathProvider] — protocol for path-info callables
- [`AutoIncrementFilenameProvider`][redsun.storage.AutoIncrementFilenameProvider] — concrete filename strategy
- [`StaticPathProvider`][redsun.storage.StaticPathProvider] — concrete path provider
- [`DeviceStorageInfo`][redsun.storage.DeviceStorageInfo] — storage capability declared by a device
- [`StorageInfo`][redsun.storage.StorageInfo] — fully resolved storage location produced by the application
- [`PrepareInfo`][redsun.storage.PrepareInfo] — typed container passed to `prepare` methods
- [`StorageContext`][redsun.storage.StorageContext] — shared presenter-level storage coordination object
- [`HasStorage`][redsun.storage.HasStorage] — protocol for devices that declare storage capability
- [`make_writer`][redsun.storage.make_writer] — SDK factory for constructing a writer from a `StorageInfo`

Devices declare storage capability by implementing `storage_info()`:

```python
from redsun.storage import DeviceStorageInfo


class MyDetector:
    def storage_info(self) -> DeviceStorageInfo:
        return DeviceStorageInfo(format_hint="application/x-zarr")
```
"""

from __future__ import annotations

from redsun.storage._base import FrameSink, SourceInfo, Writer
from redsun.storage._context import StorageContext
from redsun.storage._factory import make_writer
from redsun.storage._path import (
    AutoIncrementFilenameProvider,
    FilenameProvider,
    PathInfo,
    PathProvider,
    StaticPathProvider,
)
from redsun.storage._prepare import (
    DeviceStorageInfo,
    HasStorage,
    PrepareInfo,
    StorageInfo,
)
from redsun.storage.protocols import (
    DeviceMetadata,
    PDeviceStorageInfo,
    PStorageInfo,
    StorageMetadata,
)

__all__ = [
    # base
    "Writer",
    "SourceInfo",
    "FrameSink",
    # path
    "PathInfo",
    "FilenameProvider",
    "PathProvider",
    "AutoIncrementFilenameProvider",
    "StaticPathProvider",
    # prepare
    "DeviceStorageInfo",
    "StorageInfo",
    "PrepareInfo",
    # protocols
    "PDeviceStorageInfo",
    "PStorageInfo",
    "DeviceMetadata",
    "StorageMetadata",
    # context
    "StorageContext",
    # factory
    "make_writer",
    # has storage
    "HasStorage",
]
