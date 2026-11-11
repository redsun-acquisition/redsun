"""Tests for how a process pool sends calls, replaces crashed workers and stops, with stand-in workers."""

from __future__ import annotations

import multiprocessing
import sys
import threading
from typing import TYPE_CHECKING, Any

import pytest

from redsun.compute import BrokenPool, ProcessPool, WorkerCrashed
from redsun.compute._channel import Channel
from redsun.compute._processes import MAX_RESTARTS, ChannelFailed, PipeClosed, Worker
from redsun.services import Service
from tests.sdk.compute.helpers import wait_then_return

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from multiprocessing.connection import Listener

    from redsun.compute import Priority, ProcessExecutor


def add(a: int, b: int) -> int:
    """Return the sum."""
    return a + b


def fit(lock: object) -> None:
    """Stand for a call whose argument is handed to a worker."""


def crash() -> None:
    """Stand for a call that ends the worker running it."""


def hang() -> None:
    """Stand for a call that runs until its worker is stopped."""


def short_of_memory() -> None:
    """Stand for a call whose ring this process cannot make."""


def fail() -> None:
    """Raise an error that is not about the pipe."""
    raise OSError("the disk is full")


class FakeService:
    """Stands in for a worker's service: records that it was stopped."""

    def __init__(self, priority: Priority) -> None:
        self.priority = priority
        self.stopped = threading.Event()

    def stop(self) -> None:
        """Mark the process stopped."""
        self.stopped.set()


class FakeWorker:
    """Runs calls in this process; `crash` ends it and `hang` runs until it stops."""

    def __init__(self, priority: Priority) -> None:
        self.service = FakeService(priority)
        self.sent: list[Callable[..., Any]] = []
        self.busy = threading.Event()

    def call(
        self, fn: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> Any:
        """Return what *fn* returns, or raise `PipeClosed` as a worker that ended would."""
        self.sent.append(fn)
        self.busy.set()
        if fn is short_of_memory:
            raise ChannelFailed(OSError("no room for a ring"))
        if fn is crash:
            raise PipeClosed
        if fn is hang:
            self.service.stopped.wait(5)
        result = fn(*args, **kwargs)
        if self.service.stopped.is_set():
            raise PipeClosed
        return result

    def stop(self) -> None:
        """Stop the stand-in process."""
        self.service.stop()

    def stop_ended(self) -> None:
        """Stop the stand-in process after its pipe closed."""
        self.service.stop()


@pytest.fixture
def spawns(monkeypatch: pytest.MonkeyPatch) -> list[FakeWorker]:
    """Replace the workers a pool starts with stand-ins, listed as they start."""
    started: list[FakeWorker] = []

    def spawn(
        listener: Listener,
        authkey: bytes,
        *,
        env: Mapping[str, str],
        priority: Priority,
        stop_timeout: float,
    ) -> FakeWorker:
        worker = FakeWorker(priority)
        started.append(worker)
        return worker

    monkeypatch.setattr("redsun.compute._processes.spawn_worker", spawn)
    return started


def test_a_call_ending_three_workers_fails_and_the_rest_run(
    spawns: list[FakeWorker],
) -> None:
    """Fail a call with WorkerCrashed once it has ended 3 workers, and keep serving others."""
    with ProcessPool(1) as pool:
        crashing = pool.submit(crash)
        other = pool.submit(add, 2, 3)
        error = crashing.exception(timeout=5)
        assert isinstance(error, WorkerCrashed)
        assert str(error) == "the call ended 3 workers"
        assert other.result(timeout=5) == 5
    assert len(spawns) == 1 + 3
    assert all(worker.service.stopped.is_set() for worker in spawns)


def test_restarting_too_often_breaks_the_pool(spawns: list[FakeWorker]) -> None:
    """Break the pool on the sixth restart within 60 s, failing calls and refusing new ones."""
    with ProcessPool(1) as pool:
        first = pool.submit(crash)
        second = pool.submit(crash)
        queued = pool.submit(add, 1, 2)
        assert isinstance(first.exception(timeout=5), WorkerCrashed)
        assert isinstance(second.exception(timeout=5), (WorkerCrashed, BrokenPool))
        assert isinstance(queued.exception(timeout=5), BrokenPool)
        with pytest.raises(BrokenPool, match="restarted more than 5 times in 60 s"):
            pool.submit(add, 1, 2)
    assert len(spawns) == 1 + 5


def test_cancel_works_until_a_worker_takes_the_call(spawns: list[FakeWorker]) -> None:
    """Cancel a queued call while the only worker is busy, and never send it."""
    gate = threading.Event()
    started = threading.Event()
    with ProcessPool(1) as pool:
        running = pool.submit(wait_then_return, gate, True, started)
        assert started.wait(5)
        queued = pool.submit(add, 1, 2)
        assert queued.cancel()
        gate.set()
        assert running.result(timeout=5) is True
    assert spawns[0].sent == [wait_then_return]


def test_a_call_running_at_teardown_restarts_nothing(
    spawns: list[FakeWorker],
) -> None:
    """Fail a running call with BrokenPool at teardown and spawn no replacement."""
    pool = ProcessPool(1)
    pool.start()
    running = pool.submit(hang)
    assert spawns[0].busy.wait(5)
    pool.shutdown(wait=False, cancel_futures=True)
    error = running.exception(timeout=5)
    assert isinstance(error, BrokenPool)
    assert str(error) == "the pool shut down"
    assert len(spawns) == 1


def test_shutdown_with_wait_lets_running_calls_finish(
    spawns: list[FakeWorker],
) -> None:
    """Finish the running call before stopping the worker when shutdown waits."""
    gate = threading.Event()
    started = threading.Event()
    pool = ProcessPool(1)
    pool.start()
    running = pool.submit(wait_then_return, gate, True, started)
    assert started.wait(5)
    opener = threading.Timer(0.2, gate.set)
    opener.start()
    pool.shutdown(wait=True)
    opener.join()
    assert running.result(timeout=0) is True
    assert spawns[0].service.stopped.is_set()


def test_an_error_the_call_raises_restarts_nothing(spawns: list[FakeWorker]) -> None:
    """Fail a call with the OSError it raised in the worker, and keep the worker."""
    with ProcessPool(1) as pool:
        error = pool.submit(fail).exception(timeout=5)
    assert isinstance(error, OSError)
    assert not isinstance(error, PipeClosed)
    assert len(spawns) == 1


def test_a_second_shutdown_does_nothing(spawns: list[FakeWorker]) -> None:
    """Shut a pool down twice without error, its workers stopped after the first."""
    pool = ProcessPool(2)
    pool.start()
    pool.shutdown()
    pool.shutdown()
    assert len(spawns) == 2
    assert all(worker.service.stopped.is_set() for worker in spawns)


def test_a_failure_in_this_process_fails_the_call_and_counts_no_restart(
    spawns: list[FakeWorker],
) -> None:
    """Fail a call with this process's own error, replace its worker, and count no restart."""
    with ProcessPool(1) as pool:
        for _ in range(MAX_RESTARTS + 1):
            error = pool.submit(short_of_memory).exception(timeout=5)
            assert type(error) is OSError
        assert pool.submit(add, 2, 3).result(timeout=5) == 5
    assert len(spawns) == 1 + MAX_RESTARTS + 1
    assert spawns[0].service.stopped.is_set()


@pytest.mark.parametrize(
    ("error", "raised"),
    [
        (EOFError(), PipeClosed),
        (BrokenPipeError(), PipeClosed),
        (ConnectionResetError(), PipeClosed),
        (OSError("no room for a ring"), ChannelFailed),
        (FileNotFoundError("no such ring"), ChannelFailed),
    ],
)
def test_only_a_closed_pipe_counts_as_a_worker_gone(
    monkeypatch: pytest.MonkeyPatch, error: Exception, raised: type[Exception]
) -> None:
    """Raise PipeClosed for a pipe the worker closed, and ChannelFailed for any other channel error."""

    def refuse(*args: object) -> None:
        raise error

    monkeypatch.setattr(Channel, "send", refuse)
    here, there = multiprocessing.Pipe()
    worker = Worker(Service("worker"), Channel(here))
    try:
        with pytest.raises(raised):
            worker.call(add, (1, 2), {})
    finally:
        worker.channel.close()
        there.close()


def test_free_threaded_fallback_uses_threads(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run calls on threads of this process, after a pickle round trip, when the GIL is off."""
    monkeypatch.setattr(sys, "_is_gil_enabled", lambda: False, raising=False)
    with ProcessPool(2) as pool:
        assert (
            pool.submit(threading.get_ident).result(timeout=5) != threading.get_ident()
        )
        assert isinstance(
            pool.submit(fit, threading.Lock()).exception(timeout=5), TypeError
        )


def test_inline_processes_catches_an_unpicklable_argument(
    inline_processes: ProcessExecutor,
) -> None:
    """Fail a call whose argument could not reach a real worker."""
    assert isinstance(
        inline_processes.submit(fit, threading.Lock()).exception(), TypeError
    )
