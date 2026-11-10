"""Tests for the executor a component submits its calls through."""

from __future__ import annotations

import logging
import threading

import pytest

from redsun.compute import ThreadExecutor, ThreadPool
from redsun.compute._executor import PoolExecutor


def wait_then_return(gate: threading.Event, value: int) -> int:
    """Wait for *gate*, then return *value*."""
    gate.wait(5)
    return value


def test_an_executor_reads_its_pool_class() -> None:
    """Read pool_type from the type argument."""
    assert ThreadExecutor.pool_type is ThreadPool


def test_a_subclass_without_a_pool_type_is_refused() -> None:
    """Refuse a PoolExecutor subclass that names no pool class."""
    with pytest.raises(TypeError):
        type("Loose", (PoolExecutor,), {})


def test_submit_counts_under_the_owner(inline_threads: ThreadExecutor) -> None:
    """Run a call and report the owner's counts."""
    assert inline_threads.submit(pow, 2, 5).result() == 32
    assert inline_threads.usage().completed == 1


def test_usage_is_zero_before_the_first_call(inline_threads: ThreadExecutor) -> None:
    """Report zero counts for an owner that made no call."""
    assert inline_threads.usage().completed == 0


def test_shutdown_is_scoped_to_the_owner() -> None:
    """Cancel only this owner's waiting calls and keep the pool serving others."""
    pool = ThreadPool(1)
    mine, other = ThreadExecutor(pool, "mine"), ThreadExecutor(pool, "other")
    waiting = mine.submit(int, "1")
    kept = other.submit(int, "2")
    mine.shutdown(wait=False, cancel_futures=True)
    assert waiting.cancelled()
    with pytest.raises(RuntimeError):
        mine.submit(int, "3")
    pool.start()
    assert kept.result(timeout=5) == 2
    pool.shutdown()


def test_shutdown_before_the_pool_starts_does_not_wait() -> None:
    """Return from a waiting shutdown even though the pool has not started."""
    pool = ThreadPool(1)
    executor = ThreadExecutor(pool, "early")
    executor.submit(int, "1")
    finished = threading.Thread(target=executor.shutdown)
    finished.start()
    finished.join(5)
    alive = finished.is_alive()
    pool.shutdown()
    assert not alive


def test_cancelling_shutdown_does_not_wait_for_other_owners() -> None:
    """Return from a cancelling shutdown while another owner holds the only worker."""
    gate = threading.Event()
    with ThreadPool(1) as pool:
        busy, mine = ThreadExecutor(pool, "busy"), ThreadExecutor(pool, "mine")
        busy.submit(wait_then_return, gate, 1)
        waiting = mine.submit(int, "1")
        finished = threading.Thread(
            target=mine.shutdown, kwargs={"cancel_futures": True}
        )
        finished.start()
        finished.join(5)
        alive = finished.is_alive()
        gate.set()
    assert not alive
    assert waiting.cancelled()


def test_shutdown_waits_for_a_running_call() -> None:
    """Block a waiting shutdown until the owner's running call returns."""
    gate = threading.Event()
    with ThreadPool(1) as pool:
        executor = ThreadExecutor(pool, "running")
        future = executor.submit(wait_then_return, gate, 4)
        finished = threading.Thread(target=executor.shutdown)
        finished.start()
        finished.join(0.2)
        waited = finished.is_alive()
        gate.set()
        finished.join(5)
    assert waited
    assert not finished.is_alive()
    assert future.result() == 4


def test_then_drops_callbacks_after_shutdown(caplog: pytest.LogCaptureFixture) -> None:
    """Drop a callback whose owner was shut down while its call ran."""
    caplog.set_level(logging.DEBUG, logger="redsun")
    gate = threading.Event()
    got: list[int] = []
    with ThreadPool(1) as pool:
        executor = ThreadExecutor(pool, "gone")
        future = executor.submit(wait_then_return, gate, 7)
        future.then(got.append)
        executor.shutdown(wait=False)
        gate.set()
        future.result(timeout=5)
    assert got == []
    assert any(
        "gone" in r.getMessage() for r in caplog.records if r.levelno == logging.DEBUG
    )


async def test_run_awaits_the_result(inline_threads: ThreadExecutor) -> None:
    """Await a call's result through run."""
    assert await inline_threads.run(pow, 3, 2) == 9


def test_map_comes_from_executor(inline_threads: ThreadExecutor) -> None:
    """Map over an iterable with the standard Executor.map."""
    assert list(inline_threads.map(abs, [-1, -2])) == [1, 2]
