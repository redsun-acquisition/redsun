# SPDX-License-Identifier: Apache-2.0
# Portions of this package are structurally inspired by ophyd-async
# (https://github.com/bluesky/ophyd-async, SPDX-License-Identifier: BSD-3-Clause),
# developed by the Bluesky collaboration.
# See storage/_path.py (path/filename providers) and storage/_base.py (SharedDetectorWriter)
# for the specific files where this inspiration applies.

from __future__ import annotations

from redsun.storage._base import PrepareInfo, SharedDetectorWriter
from redsun.storage._factory import create_writer
from redsun.storage._metadata_callback import handle_descriptor_metadata
from redsun.storage._path import (
    FilenameProvider,
    PathInfo,
    PathProvider,
    SessionPathProvider,
)
from redsun.storage.protocols import HasMetadata, HasWriterLogic

__all__ = [
    "FilenameProvider",
    "HasMetadata",
    "HasWriterLogic",
    "PathInfo",
    "PathProvider",
    "PrepareInfo",
    "SessionPathProvider",
    "SharedDetectorWriter",
    "create_writer",
    "handle_descriptor_metadata",
]
