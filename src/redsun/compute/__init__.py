"""Background computation: pools that run calls off the main thread."""

from __future__ import annotations

from ._cores import Preset
from ._executor import ThreadExecutor
from ._future import BrokenPool, Future
from ._limits import Limits
from ._threads import ThreadPool, ThreadPoolSettings
from ._usage import OwnerUsage, Usage

__all__ = [
    "BrokenPool",
    "Future",
    "Limits",
    "OwnerUsage",
    "Preset",
    "ThreadExecutor",
    "ThreadPool",
    "ThreadPoolSettings",
    "Usage",
]
