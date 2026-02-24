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
- [`SessionPathProvider`][redsun.storage.SessionPathProvider] — structured session-scoped path provider
- [`DeviceStorageInfo`][redsun.storage.DeviceStorageInfo] — storage capability declared by a device
- [`StorageInfo`][redsun.storage.StorageInfo] — fully resolved storage location produced by the application
- [`PrepareInfo`][redsun.storage.PrepareInfo] — typed container passed to `prepare` methods
- [`HasStorage`][redsun.storage.HasStorage] — protocol for devices that declare storage capability
- [`make_writer`][redsun.storage.make_writer] — return the singleton writer for a URI and MIME type

Devices declare storage capability by implementing `storage_info()`:

```python
from redsun.storage import DeviceStorageInfo


class MyDetector:
    def storage_info(self) -> DeviceStorageInfo:
        return DeviceStorageInfo(mimetype="application/x-zarr")
```
"""

from __future__ import annotations

from redsun.storage._base import FrameSink, SourceInfo, Writer
from redsun.storage._factory import make_writer
from redsun.storage._info import (
    DeviceStorageInfo,
    HasStorage,
    PrepareInfo,
    StorageInfo,
)
from redsun.storage._path import (
    FilenameProvider,
    PathInfo,
    PathProvider,
    SessionPathProvider,
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
    "SessionPathProvider",
    # prepare
    "DeviceStorageInfo",
    "StorageInfo",
    "PrepareInfo",
    # protocols
    "PDeviceStorageInfo",
    "PStorageInfo",
    "DeviceMetadata",
    "StorageMetadata",
    # factory
    "make_writer",
    # has storage
    "HasStorage",
]
