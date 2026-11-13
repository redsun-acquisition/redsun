"""Tests for the process pool, run inline and with worker processes."""

from __future__ import annotations

import logging
import multiprocessing
import os
import pickle
import signal
import sys
import time
from collections import Counter
from concurrent.futures import Future, wait
from concurrent.futures.process import BrokenProcessPool
from functools import partial
from typing import TYPE_CHECKING

import pytest
from mock_pkg.compute_calls import (
    add,
    crash,
    current_priority,
    environment,
    log_debug,
    log_error,
    make_lock,
    pid,
    spin,
    spin_for,
)

from redsun.compute import BrokenPool, ProcessExecutor, ProcessPool, WorkerCrashed

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from redsun.compute import Priority

LOW = 0x4000 if sys.platform == "win32" else 10


class RecordingHandler(logging.Handler):
    """Keeps every record it is given, whatever its level."""

    def __init__(self) -> None:
        super().__init__(logging.NOTSET)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        """Keep *record*."""
        self.records.append(record)


@pytest.fixture
def worker_records() -> Generator[RecordingHandler, None, None]:
    """Record what is filed under redsun.workers.stack, at any level."""
    handler = RecordingHandler()
    pool_logger = logging.getLogger("redsun.workers.stack")
    pool_logger.addHandler(handler)
    yield handler
    pool_logger.removeHandler(handler)


@pytest.fixture
def session_level() -> Generator[None, None, None]:
    """Put back the level of the redsun logger after the test."""
    session_logger = logging.getLogger("redsun")
    found = session_logger.level
    yield
    session_logger.setLevel(found)


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


def test_a_closure_a_bound_method_or_a_partial_of_one_is_refused_at_submit() -> None:
    """Refuse a closure, a bound method and a partial of a closure at submit."""
    pool = ProcessPool(0)

    def local() -> int:
        return 1

    refused: tuple[Callable[..., object], ...] = (
        local,
        Counter().most_common,
        partial(local),
    )
    for fn in refused:
        with pytest.raises(TypeError, match="send a function defined at module level"):
            pool.submit(fn)
    pool.shutdown()


def test_a_function_from_the_script_being_run_is_refused() -> None:
    """Refuse a function defined in `__main__`, plain or inside a partial."""
    pool = ProcessPool(0)

    def in_script() -> int:
        return 1

    in_script.__qualname__ = "in_script"
    in_script.__module__ = "__main__"
    for fn in (in_script, partial(in_script)):
        with pytest.raises(TypeError, match="script being run"):
            pool.submit(fn)
    pool.shutdown()


def test_inline_processes_catches_an_unpicklable_argument(
    inline_processes: ProcessExecutor,
) -> None:
    """Fail a call whose argument holds a lock with pickle's TypeError."""
    future = inline_processes.submit(add, make_lock(), 1)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="cannot pickle"):
        future.result()


def test_an_inline_pool_catches_an_unpicklable_result() -> None:
    """Fail a call whose result cannot be pickled."""
    with ProcessPool(0) as pool, pytest.raises(TypeError, match="cannot pickle"):
        pool.submit(make_lock).result(timeout=1)


def test_an_unpicklable_argument_before_start_fails_alone() -> None:
    """Fail only the call whose argument cannot be pickled when a pool that queued it starts."""
    pool = ProcessPool(0)
    bad = pool.submit(add, 1, make_lock())  # type: ignore[arg-type]
    good = pool.submit(add, 2, 3)
    pool.start()
    assert isinstance(bad.exception(timeout=1), TypeError)
    assert good.result(timeout=1) == 5
    pool.shutdown()


@pytest.mark.processes
def test_a_worker_pool_fails_a_call_with_an_unpicklable_argument() -> None:
    """Fail a call whose argument holds a lock with pickle's TypeError, and run the next."""
    with ProcessPool(1) as pool:
        future = pool.submit(add, 1, make_lock())  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="cannot pickle"):
            future.result(timeout=30)
        assert pool.submit(add, 2, 3).result(timeout=30) == 5
    pool.shutdown()


@pytest.mark.processes
def test_a_worker_limits_the_libraries_a_call_loads_later() -> None:
    """Set the thread count variables of OpenMP, OpenBLAS and MKL to 1 in a worker."""
    names = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
    with ProcessPool(1) as pool:
        values = [pool.submit(environment, name).result(timeout=30) for name in names]
    pool.shutdown()
    assert values == ["1", "1", "1"]


@pytest.mark.processes
def test_a_worker_runs_the_call_in_another_process() -> None:
    """Return a result computed in a process other than the test's."""
    with ProcessPool(1) as pool:
        assert pool.submit(pid).result(timeout=30) != os.getpid()
    pool.shutdown()


@pytest.mark.processes
@pytest.mark.parametrize("priority", ["low", "normal"])
def test_workers_run_at_the_pool_priority(priority: Priority) -> None:
    """Run workers at the low priority, or at the test process's own for normal."""
    expected = LOW if priority == "low" else current_priority()
    with ProcessPool(1, priority=priority) as pool:
        assert pool.submit(current_priority).result(timeout=30) == expected
    pool.shutdown()


@pytest.mark.processes
@pytest.mark.skipif(
    sys.platform == "win32"
    or os.geteuid() == 0
    or os.getpriority(os.PRIO_PROCESS, 0) <= -10,
    reason="raising priority is allowed, or the process runs at high priority already",
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
    worker_records: RecordingHandler, session_level: None
) -> None:
    """Drop a worker's debug record when the session logs at INFO."""
    logging.getLogger("redsun").setLevel(logging.INFO)
    with ProcessPool(1, log_name="redsun.workers.stack") as pool:
        pool.submit(log_debug, "noise").result(timeout=30)
    pool.shutdown()
    assert not worker_records.records


@pytest.mark.processes
def test_a_record_at_the_session_level_reaches_the_session(
    worker_records: RecordingHandler, session_level: None
) -> None:
    """File a worker's debug record under its pool's logger when the session logs at DEBUG."""
    logging.getLogger("redsun").setLevel(logging.DEBUG)
    with ProcessPool(1, log_name="redsun.workers.stack") as pool:
        pool.submit(log_debug, "detail").result(timeout=30)
    pool.shutdown()
    assert [r.getMessage() for r in worker_records.records] == ["detail"]


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
def test_shutdown_returns_once_the_running_calls_are_done() -> None:
    """Return from shutdown when the running call ends, not after stop_timeout, with calls cancelled."""
    pool = ProcessPool(1, stop_timeout=30.0)
    pool.start()
    assert pool.submit(add, 1, 1).result(timeout=30) == 2
    pool.submit(spin_for, 0.5)
    for _ in range(3):
        pool.submit(add, 1, 1)
    started = time.monotonic()
    pool.shutdown()
    assert time.monotonic() - started < 15


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


@pytest.mark.processes
def test_a_crash_fails_every_unfinished_call_and_the_pool_recovers() -> None:
    """Fail the crashing call and its neighbour with WorkerCrashed, then run the next call."""
    with ProcessPool(2) as pool:
        executor = ProcessExecutor(pool, "owner")
        # both workers up first: the standard pool watches only the workers it had when it last woke
        wait([executor.submit(add, 0, 0) for _ in range(2)], timeout=30)
        neighbour = executor.submit(spin_for, 5.0)
        crashing = executor.submit(crash, 3)
        for future in (crashing, neighbour):
            with pytest.raises(WorkerCrashed) as caught:
                future.result(timeout=30)
            assert isinstance(caught.value.__cause__, BrokenProcessPool)
        assert executor.submit(add, 1, 2).result(timeout=30) == 3
        assert executor.usage().crashed == 2
    pool.shutdown()


@pytest.mark.processes
def test_calls_after_a_crash_run_on_the_new_executor() -> None:
    """Run calls submitted while the pool replaces its executor."""
    with ProcessPool(1) as pool:
        with pytest.raises(WorkerCrashed):
            pool.submit(crash, 3).result(timeout=30)
        later = [pool.submit(add, i, i) for i in range(5)]
        assert [f.result(timeout=30) for f in later] == [0, 2, 4, 6, 8]
    pool.shutdown()


@pytest.mark.processes
def test_repeated_crashes_break_the_pool() -> None:
    """Break the pool after more than 3 replacements in 60 s and refuse later calls."""
    with ProcessPool(1) as pool:
        for _ in range(4):
            with pytest.raises(WorkerCrashed):
                pool.submit(crash, 3).result(timeout=30)
        with pytest.raises(BrokenPool, match="replaced more than 3 times in 60 s"):
            pool.submit(add, 1, 1)
    pool.shutdown()


@pytest.mark.processes
def test_an_answer_that_cannot_be_pickled_fails_only_its_call() -> None:
    """Fail a call returning a lock with TypeError or PicklingError and keep the workers."""
    with ProcessPool(1) as pool:
        before = pool.submit(pid).result(timeout=30)
        with pytest.raises((TypeError, pickle.PicklingError)):
            pool.submit(make_lock).result(timeout=30)
        assert pool.submit(pid).result(timeout=30) == before
    pool.shutdown()


@pytest.mark.processes
def test_a_crashed_call_can_submit_again_from_its_callback() -> None:
    """Return the result of a call submitted from the done-callback of a crashed call."""
    with ProcessPool(1) as pool:
        again: Future[Future[int]] = Future()
        pool.submit(crash, 3).add_done_callback(
            lambda _: again.set_result(pool.submit(add, 1, 1))
        )
        assert again.result(timeout=30).result(timeout=30) == 2
    pool.shutdown()


@pytest.mark.processes
def test_a_call_after_an_idle_worker_died_runs_on_new_workers() -> None:
    """Return a result from a call submitted after an idle worker was killed."""
    with ProcessPool(1) as pool:
        worker = pool.submit(pid).result(timeout=30)
        os.kill(worker, signal.SIGTERM)
        while any(p.pid == worker for p in multiprocessing.active_children()):
            time.sleep(0.05)
        deadline = time.monotonic() + 30
        while True:
            # the standard pool notices the death on its own thread, so a call
            # may still reach the dying workers and crash with them
            try:
                assert pool.submit(add, 2, 2).result(timeout=30) == 4
                break
            except WorkerCrashed:
                assert time.monotonic() < deadline
    pool.shutdown()
