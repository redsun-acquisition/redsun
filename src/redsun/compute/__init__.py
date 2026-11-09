"""Background computation."""

from __future__ import annotations

from typing import Final

from ._budget import Budget, Preset, budget, physical_cores, split
from ._deliver import deliver
from ._executors import ThreadExecutor

__all__ = [
    "Budget",
    "Preset",
    "ThreadExecutor",
    "budget",
    "deliver",
    "physical_cores",
    "split",
]

EXECUTORS: Final = (ThreadExecutor,)
"""The executor classes a session passes to a component's constructor."""
