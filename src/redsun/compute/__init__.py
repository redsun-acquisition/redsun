"""Background computation: pools that run calls off the main thread."""

from __future__ import annotations

from ._future import BrokenPool, Future, WorkerCrashed
from ._processes import ProcessExecutor, ProcessPool
from ._settings import (
    ComputeSettings,
    Limits,
    Preset,
    Priority,
    ProcessPoolSettings,
    ThreadPoolSettings,
)
from ._threads import ThreadExecutor, ThreadPool
from ._usage import OwnerUsage

__all__ = [
    "BrokenPool",
    "ComputeSettings",
    "Future",
    "Limits",
    "OwnerUsage",
    "Preset",
    "Priority",
    "ProcessExecutor",
    "ProcessPool",
    "ProcessPoolSettings",
    "ThreadExecutor",
    "ThreadPool",
    "ThreadPoolSettings",
    "WorkerCrashed",
]
