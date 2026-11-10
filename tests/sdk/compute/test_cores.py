"""Tests for the compute cores and the presets."""

from __future__ import annotations

import logging

import pytest

from redsun.compute import Preset, ThreadPoolSettings
from redsun.compute._settings import compute_cores, physical_cores, split


@pytest.mark.parametrize(
    ("preset", "cores", "threads", "native"),
    [
        ("latency", 15, 1, 15),
        ("balanced", 15, 3, 5),
        ("balanced", 4, 2, 2),
        ("balanced", 1, 2, 1),
        ("throughput", 15, 15, 1),
    ],
)
def test_presets_split_the_compute_cores(
    preset: Preset, cores: int, threads: int, native: int
) -> None:
    """Split the compute cores between pool threads and native threads per preset."""
    assert split(preset, cores) == ThreadPoolSettings(threads, native)


@pytest.mark.parametrize(
    ("physical", "cap", "reserve", "expected"),
    [
        (16, None, None, 15),
        (16, 12, None, 12),
        (16, None, [0, 1], 14),
        (1, None, None, 1),
    ],
)
def test_compute_cores(
    physical: int, cap: int | None, reserve: list[int] | None, expected: int
) -> None:
    """Take the reserve out of the physical cores, cap the rest and keep at least one."""
    assert compute_cores(physical, cap=cap, reserve=reserve) == expected


def test_physical_cores_falls_back_with_a_warning(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Fall back to os.cpu_count and warn with the error as text when reading fails."""
    monkeypatch.setattr("sys.platform", "plan9")
    monkeypatch.setattr("os.cpu_count", lambda: 6)
    assert physical_cores() == 6
    (record,) = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert record.exc_info is None and record.args == ()
