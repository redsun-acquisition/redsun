# SPDX-License-Identifier: Apache-2.0
# The file and path providers are inspired by ophyd-async
# (https://github.com/bluesky/ophyd-async), developed by the Bluesky collaboration.
# ophyd-async is licensed under the BSD 3-Clause License.

from __future__ import annotations

from dataclasses import dataclass

from redsun.storage._base import FrameSink, Writer
from redsun.storage._path import (
    FilenameProvider,
    PathInfo,
    PathProvider,
    SessionPathProvider,
)
from redsun.storage.metadata import clear_metadata, register_metadata


@dataclass
class PrepareInfo:
    """Plan-time information passed to device ``prepare()`` methods.

    !!! warning

        These are still experimental. New fields may be added
        or existing fields may change.

    """

    capacity: int = 0
    """Number of frames to prepare for.  ``0`` means unlimited."""

    write_forever: bool = False
    """Whether the device should prepare to write indefinitely (e.g. for live streaming)."""


__all__ = [
    "PathInfo",
    "FilenameProvider",
    "PathProvider",
    "SessionPathProvider",
    "register_metadata",
    "FrameSink",
    "clear_metadata",
    "PrepareInfo",
    "Writer",
]
