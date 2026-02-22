# SPDX-License-Identifier: Apache-2.0
# The design of this subpackage is heavily inspired by ophyd-async
# (https://github.com/bluesky/ophyd-async), developed by the Bluesky collaboration.
# ophyd-async is licensed under the BSD 3-Clause License.
# No source code from ophyd-async has been copied; the architectural patterns
# (shared writer, path providers, FrameSink, StorageProxy protocol) were
# studied and independently re-implemented to fit the redsun model.

"""Storage infrastructure for redsun devices.

This subpackage provides the dependency-free primitives for storage:

- [`Writer`][redsun.storage.Writer] — abstract base class for storage backends
- [`FrameSink`][redsun.storage.FrameSink] — device-facing handle for pushing frames
- [`SourceInfo`][redsun.storage.SourceInfo] — per-device frame metadata
- [`PathInfo`][redsun.storage.PathInfo] — storage path and configuration for one device
- [`FilenameProvider`][redsun.storage.FilenameProvider] — protocol for filename callables
- [`PathProvider`][redsun.storage.PathProvider] — protocol for path-info callables
- [`StaticFilenameProvider`][redsun.storage.StaticFilenameProvider],
  [`UUIDFilenameProvider`][redsun.storage.UUIDFilenameProvider],
  [`AutoIncrementFilenameProvider`][redsun.storage.AutoIncrementFilenameProvider] — concrete filename strategies
- [`StaticPathProvider`][redsun.storage.StaticPathProvider] — concrete path provider
- [`StorageProxy`][redsun.storage.StorageProxy] — protocol implemented by all storage backends
- [`StorageDescriptor`][redsun.storage.StorageDescriptor] — descriptor for declaring `storage` on a device
- [`HasStorage`][redsun.storage.HasStorage] — protocol for devices that have opted in to storage

Concrete backend classes (e.g. `ZarrWriter`) are internal
implementation details and are not exported from this package.
The application container is responsible for selecting and instantiating
the correct backend based on the session configuration.

Devices that require storage declare it explicitly in their class body:

```python
from redsun.storage import StorageDescriptor


class MyDetector(Device):
    storage = StorageDescriptor()
```
"""

from __future__ import annotations

from redsun.storage._base import FrameSink, SourceInfo, Writer
from redsun.storage._path import (
    AutoIncrementFilenameProvider,
    FilenameProvider,
    PathInfo,
    PathProvider,
    StaticFilenameProvider,
    StaticPathProvider,
    UUIDFilenameProvider,
)
from redsun.storage._proxy import (
    HasStorage,
    StorageDescriptor,
    StorageProxy,
    require_storage,
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
    "StaticFilenameProvider",
    "UUIDFilenameProvider",
    "AutoIncrementFilenameProvider",
    "StaticPathProvider",
    # proxy / descriptor
    "StorageProxy",
    "StorageDescriptor",
    "HasStorage",
    "require_storage",
]
