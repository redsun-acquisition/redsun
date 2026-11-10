"""Tests for the native thread limits and the pool resource."""

from __future__ import annotations

import importlib
import logging
import sys
from typing import TYPE_CHECKING

import pytest
from threadpoolctl import threadpool_info, threadpool_limits

from redsun.compute import Limits, ThreadPool, ThreadPoolSettings

if TYPE_CHECKING:
    from collections.abc import Generator

importlib.import_module("numpy")


@pytest.fixture
def native_limits_kept() -> Generator[None, None, None]:
    """Put the process-wide native thread limits back after the test."""
    found = threadpool_limits(limits=None)
    yield
    found.restore_original_limits()


def test_limits_apply_once_and_restore() -> None:
    """Limit native pools and the switch interval, then put both back."""
    found_interval = sys.getswitchinterval()
    found = threadpool_info()
    limits = Limits(switch_interval_ms=1.0)
    try:
        limits.apply(1)
        limits.apply(4)
        assert sys.getswitchinterval() == 0.001
        assert all(pool["num_threads"] == 1 for pool in threadpool_info())
    finally:
        limits.restore()
        limits.restore()
    assert sys.getswitchinterval() == found_interval
    assert threadpool_info() == found


@pytest.mark.usefixtures("native_limits_kept")
def test_pool_threads_apply_the_limit() -> None:
    """Apply the native limit in each pool thread through the initializer."""
    with ThreadPool(1, initializer=Limits().initializer(1)) as pool:
        seen = pool.submit(threadpool_info).result(timeout=5)
    assert all(pool["num_threads"] == 1 for pool in seen)


@pytest.mark.usefixtures("native_limits_kept")
def test_the_resource_logs_usage_and_stops_the_pool(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Log the summary line and shut the pool down at teardown."""
    caplog.set_level(logging.INFO, logger="redsun")
    resource = ThreadPool.resource(ThreadPoolSettings(1, 1), Limits())
    pool = next(resource)
    pool.start()
    pool.submit_as("median", int, "1").result(timeout=5)
    resource.close()
    assert any(
        r.getMessage().startswith("thread pool: 1 workers, 1 calls (median 1)")
        for r in caplog.records
    )
    with pytest.raises(RuntimeError):
        pool.submit(int, "1")
