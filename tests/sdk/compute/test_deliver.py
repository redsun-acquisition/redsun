from __future__ import annotations

import logging
import sys
import threading
from concurrent.futures import Future
from typing import TYPE_CHECKING, Literal

import pytest
from psygnal import emit_queued

from redsun import slot
from redsun.compute import ThreadExecutor, deliver

if TYPE_CHECKING:
    from collections.abc import Callable


class Frontend:
    """A frontend that drains the main-thread queue."""


@pytest.fixture
def draining(monkeypatch: pytest.MonkeyPatch) -> dict[object, threading.Thread]:
    """Have a frontend built on the main thread drain the queue; clear the result to stop it."""
    drainers: dict[object, threading.Thread] = {Frontend(): threading.main_thread()}
    monkeypatch.setattr("redsun.compute._deliver.DRAINERS", drainers)
    return drainers


def test_deliver_calls_at_once_without_a_frontend(
    wait_until: Callable[..., bool],
) -> None:
    """Call the callback at once when nothing drains the queue."""
    got: list[int] = []
    deliver(ThreadExecutor(1).submit(pow, 2, 3), got.append)
    assert wait_until(lambda: got == [8])


def test_deliver_logs_a_failed_call(
    caplog: pytest.LogCaptureFixture, wait_until: Callable[..., bool]
) -> None:
    """Log a failed call once, naming the callback, and leave it uncalled."""
    got: list[int] = []
    deliver(ThreadExecutor(1).submit(int, "x"), got.append)
    assert wait_until(lambda: "ValueError" in caplog.text)
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(errors) == 1
    assert "append" in errors[0].getMessage()
    assert got == []


def test_deliver_logs_a_call_that_exits_and_keeps_the_pool(
    caplog: pytest.LogCaptureFixture, wait_until: Callable[..., bool]
) -> None:
    """Log a call raising SystemExit once and keep the pool running later calls."""
    got: list[int] = []
    executor = ThreadExecutor(1)
    deliver(executor.submit(sys.exit, 1), got.append)
    assert wait_until(lambda: "SystemExit" in caplog.text)
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert len(errors) == 1
    assert got == []
    assert executor.submit(pow, 2, 3).result(timeout=5) == 8


def test_deliver_ignores_a_cancelled_call(caplog: pytest.LogCaptureFixture) -> None:
    """Call nothing and log no error when the future was cancelled."""
    got: list[int] = []
    future: Future[int] = Future()
    deliver(future, got.append)
    future.cancel()
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert got == []


@pytest.mark.parametrize("thread", [None, "unmarked", "main", "current"])
def test_deliver_queues_for_the_main_thread_while_a_frontend_drains(
    draining: dict[object, threading.Thread],
    wait_until: Callable[..., bool],
    thread: Literal["unmarked", "main", "current"] | None,
) -> None:
    """Queue the callback for the thread the session was built on, then call it there."""
    ran_on: list[threading.Thread] = []
    release = threading.Event()
    delivered = threading.Event()

    def callback(value: int) -> None:
        ran_on.append(threading.current_thread())

    target = callback if thread == "unmarked" else slot(thread=thread)(callback)
    future = ThreadExecutor(1).submit(lambda: release.wait(5) and 8)
    # called off the main thread, as from a plan's document callback
    caller = threading.Thread(target=deliver, args=(future, target))
    caller.start()
    caller.join()
    future.add_done_callback(lambda _: delivered.set())
    release.set()
    assert delivered.wait(5)
    assert ran_on == []

    def drained() -> bool:
        emit_queued()
        return bool(ran_on)

    assert wait_until(drained)
    assert ran_on == [threading.main_thread()]


def test_deliver_drops_a_result_finishing_after_the_frontend_stops(
    caplog: pytest.LogCaptureFixture, draining: dict[object, threading.Thread]
) -> None:
    """Drop a result that finishes once its frontend stopped draining, and log it."""
    got: list[int] = []
    release = threading.Event()
    finished = threading.Event()
    future = ThreadExecutor(1).submit(lambda: release.wait(5) and 8)
    with caplog.at_level(logging.DEBUG, logger="redsun"):
        deliver(future, got.append)
        future.add_done_callback(lambda _: finished.set())
        draining.clear()
        release.set()
        assert finished.wait(5)
        emit_queued()
    assert got == []
    assert "shut down" in caplog.text


def test_deliver_keeps_the_pool_when_a_callback_exits(
    caplog: pytest.LogCaptureFixture, wait_until: Callable[..., bool]
) -> None:
    """Log a callback raising SystemExit on a pool thread and keep the pool running."""
    executor = ThreadExecutor(1)
    release = threading.Event()

    def exit_now(value: int) -> None:
        sys.exit(value)

    deliver(executor.submit(lambda: release.wait(5) and 8), exit_now)
    release.set()
    assert wait_until(lambda: "SystemExit" in caplog.text)
    assert executor.submit(pow, 2, 3).result(timeout=5) == 8
