"""Tests for the pool base, the thread pool and the per-owner counts."""

from __future__ import annotations

import re
import threading
import time
import weakref
from concurrent.futures import wait
from typing import TYPE_CHECKING, Any, final

import pytest

from redsun.compute import BrokenPool, OwnerUsage, ThreadExecutor, ThreadPool
from redsun.compute._future import PRE_START
from redsun.compute._pool import Call, Pool, PoolExecutor
from redsun.compute._usage import Counts
from tests.sdk.compute.helpers import explode, wait_then_return
from tests.sdk.helpers import automatic_collection

if TYPE_CHECKING:
    from collections.abc import Generator


def counts(usage: OwnerUsage) -> tuple[int, int, int, int]:
    """Return what an owner's calls did: queued, active, completed, failed."""
    return usage.queued, usage.active, usage.completed, usage.failed


class FlakyPool(Pool):
    """Runs calls in place, except that it cannot send a call made with 'bad'."""

    def __init__(self) -> None:
        super().__init__()
        self.starts = 0

    @classmethod
    def resource(cls) -> Generator[FlakyPool, None, None]:
        """Yield a pool."""
        yield cls()

    @property
    def pool_size(self) -> int:
        """No workers."""
        return 0

    def _start(self) -> None:
        self.starts += 1

    def _dispatch(self, call: Call[Any]) -> None:
        if call.args == ("bad",):
            raise ValueError("cannot send")
        call.run()

    def _stop(self, wait: bool, cancel_futures: bool) -> None:
        """Stop nothing."""


@final
class FlakyExecutor(PoolExecutor[FlakyPool]):
    """Submits to a FlakyPool."""


def test_calls_wait_for_start_and_run_in_order() -> None:
    """Hold calls submitted before start and run them first, in submission order."""
    ran: list[int] = []
    pool = ThreadPool(1)
    executor = ThreadExecutor(pool, "a")
    futures = [executor.submit(ran.append, n) for n in range(5)]
    pool.start()
    executor.submit(ran.append, 99).result(timeout=5)
    assert ran == [0, 1, 2, 3, 4, 99]
    assert all(f.done() for f in futures)
    pool.shutdown()


def test_result_before_start_raises() -> None:
    """Refuse result() on a call waiting for start."""
    pool = ThreadPool(1)
    future = pool.submit(int, "1")
    with pytest.raises(RuntimeError, match=re.escape(PRE_START)):
        future.result()
    pool.start()
    assert future.result(timeout=5) == 1
    pool.shutdown()


def test_cancel_before_start_leaves_the_queue() -> None:
    """Cancel a waiting call and count it out of queued."""
    pool = ThreadPool(0)
    ran: list[int] = []
    future = ThreadExecutor(pool, "a").submit(ran.append, 1)
    assert future.cancel()
    assert pool.usage().owners["a"].queued == 0
    pool.start()
    assert ran == []
    pool.shutdown()


def test_counts_per_owner() -> None:
    """Count completed and failed calls per owner, and direct calls under '<pool>'."""
    with ThreadPool(0) as pool:
        executor = ThreadExecutor(pool, "a")
        executor.submit(int, "1")
        executor.submit(int, "x")
        pool.submit(int, "2")
        usage = pool.usage()
    assert counts(usage.owners["a"]) == (0, 0, 1, 1)
    assert usage.owners["<pool>"].completed == 1
    assert usage.pool_size == 0


def test_a_long_wait_is_logged_when_the_call_starts(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Log a call that waited more than 1 s for a worker, under its owner's logger."""
    with ThreadPool(1) as pool:
        ThreadExecutor(pool, "a").submit(time.sleep, 1.2)
        ThreadExecutor(pool, "b").submit(int, "1").result(timeout=5)
    assert any(r.name == "redsun.compute.b" for r in caplog.records)


def test_a_pool_that_fails_to_start_is_broken() -> None:
    """Fail waiting calls with BrokenPool and refuse later ones when start raises."""
    pool = ThreadPool(0, initializer=explode)
    waiting = pool.submit(int, "1")
    with pytest.raises(BrokenPool, match="the pool did not start: "):
        pool.start()
    assert isinstance(waiting.exception(timeout=1), BrokenPool)
    with pytest.raises(BrokenPool):
        pool.submit(int, "1")
    pool.shutdown()


def test_shutdown_before_start_cancels_waiting_calls() -> None:
    """Cancel every waiting call when a pool that never started shuts down."""
    pool = ThreadPool(1)
    future = pool.submit(int, "1")
    pool.shutdown(cancel_futures=True)
    assert future.cancelled()
    assert wait([future], timeout=5).done == {future}
    with pytest.raises(RuntimeError, match="after shutdown"):
        pool.submit(int, "1")


def test_shutdown_can_cancel_calls_no_worker_took() -> None:
    """Cancel a call still queued for a worker and count it out of queued."""
    started = threading.Event()
    release = threading.Event()
    pool = ThreadPool(1)
    executor = ThreadExecutor(pool, "a")
    pool.start()
    running = executor.submit(wait_then_return, release, True, started)
    assert started.wait(5)
    queued = executor.submit(int, "1")
    pool.shutdown(wait=False, cancel_futures=True)
    release.set()
    assert running.result(timeout=5) is True
    assert queued.cancelled()
    assert wait([queued], timeout=5).done == {queued}
    assert counts(pool.usage().owners["a"]) == (0, 0, 1, 0)


def test_summary_names_the_busiest_owners_first() -> None:
    """Write one line with the calls per owner, the failures and the longest wait."""
    tally = Counts()
    for owner, waited, failed in [("roi", 0.2, False), ("median", 1.4, False)] + [
        ("median", 0.0, True)
    ]:
        tally.submitted(owner)
        tally.started(owner, waited)
        tally.finished(owner, failed)
    assert tally.summary("thread pool", 3) == (
        "thread pool: 3 workers, 3 calls (median 2, roi 1), 1 failed, longest idle 1.4 s"
    )


def test_a_failed_call_is_freed_without_a_collection() -> None:
    """Free a failed call's future as soon as the caller drops it."""
    with automatic_collection(False):
        with ThreadPool(1) as pool:
            future = ThreadExecutor(pool, "a").submit(int, "x")
            assert isinstance(future.exception(timeout=5), ValueError)
        ref = weakref.ref(future)
        del future
        assert ref() is None


def test_a_call_the_pool_cannot_send_fails_and_the_rest_run() -> None:
    """Fail only the waiting call that cannot be sent, and start the pool once."""
    pool = FlakyPool()
    executor = FlakyExecutor(pool, "a")
    bad = executor.submit(str, "bad")
    good = executor.submit(str, "good")
    pool.start()
    pool.start()
    assert isinstance(bad.exception(timeout=1), ValueError)
    assert good.result(timeout=1) == "good"
    assert executor.submit(str, "later").result(timeout=1) == "later"
    assert pool.starts == 1
    assert executor.usage().failed == 1
    assert executor.usage().queued == 0


def test_workers_that_break_after_start_fail_the_calls() -> None:
    """Fail a call and refuse later ones with BrokenPool when a worker's initializer raises."""
    pool = ThreadPool(1, initializer=explode)
    waiting = pool.submit(int, "1")
    pool.start()
    assert isinstance(waiting.exception(timeout=5), BrokenPool)
    with pytest.raises(BrokenPool):
        pool.submit(int, "1")
    pool.shutdown()
