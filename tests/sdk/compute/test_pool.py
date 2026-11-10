"""Tests for the pool base, the thread pool and the per-owner counts."""

from __future__ import annotations

import re
import threading
import time
from typing import TYPE_CHECKING, Annotated

import pytest
from diwire import Component

from redsun.compute import BrokenPool, OwnerUsage, ThreadPool
from redsun.compute._future import PRE_START
from redsun.compute._pool import pool_key
from redsun.compute._usage import Counts

if TYPE_CHECKING:
    pass


def explode() -> None:
    """Raise, as an initializer that cannot run."""
    raise RuntimeError("boom")


def test_calls_wait_for_start_and_run_in_order() -> None:
    """Hold calls submitted before start and run them first, in submission order."""
    ran: list[int] = []
    pool = ThreadPool(1)
    futures = [pool.submit_as("a", ran.append, n) for n in range(5)]
    pool.start()
    pool.submit_as("a", ran.append, 99).result(timeout=5)
    assert ran == [0, 1, 2, 3, 4, 99]
    assert all(f.done() for f in futures)
    pool.shutdown()


def test_result_before_start_raises() -> None:
    """Refuse result() on a call waiting for start."""
    pool = ThreadPool(1)
    future = pool.submit_as("a", int, "1")
    with pytest.raises(RuntimeError, match=re.escape(PRE_START)):
        future.result()
    pool.start()
    assert future.result(timeout=5) == 1
    pool.shutdown()


def test_cancel_before_start_leaves_the_queue() -> None:
    """Cancel a waiting call and count it out of queued."""
    pool = ThreadPool(0)
    ran: list[int] = []
    future = pool.submit_as("a", ran.append, 1)
    assert future.cancel()
    assert pool.usage().owners["a"].queued == 0
    pool.start()
    assert ran == []
    pool.shutdown()


def test_counts_per_owner() -> None:
    """Count completed and failed calls per owner, and direct calls under '<pool>'."""
    with ThreadPool(0) as pool:
        pool.submit_as("a", int, "1")
        pool.submit_as("a", int, "x")
        pool.submit(int, "2")
        usage = pool.usage()
    assert usage.owners["a"] == OwnerUsage(
        queued=0,
        active=0,
        completed=1,
        failed=1,
        longest_idle=usage.owners["a"].longest_idle,
    )
    assert usage.owners["<pool>"].completed == 1
    assert usage.pool_size == 0


def test_a_long_wait_is_logged_when_the_call_starts(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Log a call that waited more than 1 s for a worker, under its owner's logger."""
    with ThreadPool(1) as pool:
        pool.submit_as("a", time.sleep, 1.2)
        pool.submit_as("b", int, "1").result(timeout=5)
    assert any(r.name == "redsun.compute.b" for r in caplog.records)


def test_a_pool_that_fails_to_start_is_broken() -> None:
    """Fail waiting calls with BrokenPool and refuse later ones when start raises."""
    pool = ThreadPool(1, initializer=explode)
    waiting = pool.submit_as("a", int, "1")
    with pytest.raises(BrokenPool, match="the pool did not start: "):
        pool.start()
    assert isinstance(waiting.exception(timeout=1), BrokenPool)
    with pytest.raises(BrokenPool):
        pool.submit_as("a", int, "1")
    pool.shutdown()


def test_shutdown_before_start_cancels_waiting_calls() -> None:
    """Cancel every waiting call when a pool that never started shuts down."""
    pool = ThreadPool(1)
    future = pool.submit_as("a", int, "1")
    pool.shutdown()
    assert future.cancelled()
    with pytest.raises(RuntimeError, match="after shutdown"):
        pool.submit_as("a", int, "1")


def test_shutdown_can_cancel_calls_no_worker_took() -> None:
    """Cancel a call still queued for a worker and count it out of queued."""
    release = threading.Event()
    pool = ThreadPool(1)
    pool.start()
    running = pool.submit_as("a", release.wait, 5)
    queued = pool.submit_as("a", int, "1")
    pool.shutdown(wait=False, cancel_futures=True)
    release.set()
    assert running.result(timeout=5) is True
    assert queued.cancelled()
    assert pool.usage().owners["a"] == OwnerUsage(
        queued=0,
        active=0,
        completed=1,
        failed=0,
        longest_idle=pool.usage().owners["a"].longest_idle,
    )


def test_pool_key_names_the_group() -> None:
    """Key the shared pool by its class and a group's pool by a diwire Component."""
    assert pool_key(ThreadPool, None) is ThreadPool
    assert pool_key(ThreadPool, "heavy") == Annotated[ThreadPool, Component("heavy")]


def test_summary_names_the_busiest_owners_first() -> None:
    """Write one line with the calls per owner, the failures and the longest wait."""
    counts = Counts()
    for owner, waited, failed in [("roi", 0.2, False), ("median", 1.4, False)] + [
        ("median", 0.0, True)
    ]:
        counts.submitted(owner)
        counts.started(owner, waited)
        counts.finished(owner, failed)
    assert counts.summary("thread pool", 3) == (
        "thread pool: 3 workers, 3 calls (median 2, roi 1), 1 failed, longest idle 1.4 s"
    )
