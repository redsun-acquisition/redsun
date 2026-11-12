"""Tests for the process pool, run inline and with worker processes."""

from __future__ import annotations

import logging
import os
import sys
import time
from typing import TYPE_CHECKING

import pytest
from mock_pkg.compute_calls import (
    add,
    current_priority,
    log_debug,
    log_error,
    make_lock,
    pid,
    spin,
    spin_for,
)

from redsun.compute import BrokenPool, ProcessExecutor, ProcessPool

if TYPE_CHECKING:
    from redsun.compute import Priority

EXPECTED: dict[str, int] = (
    {"low": 0x4000, "normal": 0x20}
    if sys.platform == "win32"
    else {"low": 10, "normal": 0}
)


def test_an_inline_pool_returns_the_result() -> None:
    """Return a call's result from a ProcessPool(0) after a pickling round trip."""
    with ProcessPool(0) as pool:
        assert pool.submit(add, 2, 3).result() == 5


def test_a_lambda_is_refused_at_submit() -> None:
    """Refuse a lambda with TypeError before anything is queued."""
    with ProcessPool(0) as pool:
        executor = ProcessExecutor(pool, "owner")
        with pytest.raises(TypeError, match="module level"):
            executor.submit(lambda: 1)
        assert executor.usage().queued == 0


def test_inline_processes_catches_an_unpicklable_argument(
    inline_processes: ProcessExecutor,
) -> None:
    """Fail a call whose argument holds a lock, naming the argument."""
    future = inline_processes.submit(add, make_lock(), 1)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match=r"add\(a=\.\.\.\)"):
        future.result()


@pytest.mark.processes
def test_a_worker_runs_the_call_in_another_process() -> None:
    """Return a result computed in a process other than the test's."""
    with ProcessPool(1) as pool:
        assert pool.submit(pid).result(timeout=30) != os.getpid()
    pool.shutdown()


@pytest.mark.processes
@pytest.mark.parametrize("priority", ["low", "normal"])
def test_workers_run_at_the_pool_priority(priority: Priority) -> None:
    """Read back the priority the worker's initializer set."""
    with ProcessPool(1, priority=priority) as pool:
        assert pool.submit(current_priority).result(timeout=30) == EXPECTED[priority]
    pool.shutdown()


@pytest.mark.processes
@pytest.mark.skipif(
    sys.platform == "win32" or os.geteuid() == 0, reason="raising priority is allowed"
)
def test_a_refused_priority_warns_and_runs(caplog: pytest.LogCaptureFixture) -> None:
    """Log the worker's refusal under the pool's logger and still run calls."""
    with ProcessPool(1, priority="high", log_name="redsun.workers.stack") as pool:
        assert pool.submit(add, 1, 1).result(timeout=30) == 2
    pool.shutdown()
    assert any(
        r.name == "redsun.workers.stack" and r.levelno == logging.WARNING
        for r in caplog.records
    )


@pytest.mark.processes
def test_a_worker_error_reaches_the_session_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """File a worker's logged error, traceback included, under redsun.workers.<owner>."""
    with ProcessPool(1, log_name="redsun.workers.stack") as pool:
        pool.submit(log_error, "fit failed").result(timeout=30)
    pool.shutdown()
    (record,) = [r for r in caplog.records if r.name == "redsun.workers.stack"]
    assert record.getMessage() == "fit failed"
    assert record.exc_text is not None
    assert "ZeroDivisionError" in record.exc_text
    assert record.exc_info is None


@pytest.mark.processes
def test_a_record_below_the_session_level_stays_in_the_worker(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Drop a worker's debug record when the session logs at INFO."""
    caplog.set_level(logging.INFO, logger="redsun")
    with ProcessPool(1, log_name="redsun.workers.stack") as pool:
        pool.submit(log_debug, "noise").result(timeout=30)
    pool.shutdown()
    assert not [r for r in caplog.records if r.name == "redsun.workers.stack"]


@pytest.mark.processes
def test_shutdown_ends_a_stuck_call() -> None:
    """End a call in an endless loop within stop_timeout and fail it with BrokenPool."""
    pool = ProcessPool(1, stop_timeout=1.0)
    pool.start()
    future = pool.submit(spin)
    time.sleep(2)
    started = time.monotonic()
    pool.shutdown()
    assert time.monotonic() - started < 6
    with pytest.raises(BrokenPool, match="the pool shut down"):
        future.result(timeout=5)


@pytest.mark.processes
def test_a_waiting_call_can_be_cancelled() -> None:
    """Cancel a call the busy worker has not taken, and count it nowhere."""
    with ProcessPool(1) as pool:
        executor = ProcessExecutor(pool, "owner")
        for _ in range(3):
            executor.submit(spin_for, 2.0)
        waiting = executor.submit(add, 1, 1)
        assert waiting.cancel()
        usage = executor.usage()
        assert (usage.queued, usage.active) == (0, 3)
    pool.shutdown()
