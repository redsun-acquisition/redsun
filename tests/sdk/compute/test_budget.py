from __future__ import annotations

import os

import pytest

from redsun.compute import Budget, Preset, budget, physical_cores, split


@pytest.mark.parametrize(
    ("preset", "cores", "threads", "native"),
    [
        ("latency", 12, 1, 12),
        ("balanced", 12, 3, 4),
        ("balanced", 4, 2, 2),
        ("throughput", 12, 12, 1),
        ("balanced", 1, 2, 1),
    ],
)
def test_split(preset: Preset, cores: int, threads: int, native: int) -> None:
    """Split a budget the way each preset says."""
    assert split(preset, cores) == Budget(cores, threads, native)


def test_budget_keeps_one_core_and_respects_the_cap() -> None:
    """Leave the reserved cores out and cap the rest."""
    assert budget("throughput", physical=16, cap=None, reserve=1).cores == 15
    assert budget("throughput", physical=16, cap=8, reserve=1).cores == 8


def test_physical_cores_is_at_most_the_logical_count() -> None:
    """Count physical cores, never more than the logical CPUs."""
    assert 1 <= physical_cores() <= (os.cpu_count() or 1)
