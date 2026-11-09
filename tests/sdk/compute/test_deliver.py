from __future__ import annotations

import logging
import sys
import threading
from concurrent.futures import Future
from typing import TYPE_CHECKING

import pytest
from psygnal import emit_queued

from redsun import slot
from redsun.compute import ThreadExecutor, deliver

if TYPE_CHECKING:
    from collections.abc import Callable


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


@pytest.mark.parametrize("marked", [False, True])
def test_deliver_queues_for_the_main_thread_while_a_frontend_drains(
    monkeypatch: pytest.MonkeyPatch, wait_until: Callable[..., bool], marked: bool
) -> None:
    """Hold the callback until the main thread drains the queue, then call it there."""
    monkeypatch.setattr("redsun.compute._deliver.DRAINERS", {object()})
    ran_on: list[threading.Thread] = []
    release = threading.Event()
    delivered = threading.Event()

    def callback(value: int) -> None:
        ran_on.append(threading.current_thread())

    target = slot(callback) if marked else callback
    future = ThreadExecutor(1).submit(lambda: release.wait(5) and 8)
    deliver(future, target)
    future.add_done_callback(lambda _: delivered.set())
    release.set()
    assert delivered.wait(5)
    assert ran_on == []

    def drained() -> bool:
        emit_queued()
        return bool(ran_on)

    assert wait_until(drained)
    assert ran_on == [threading.main_thread()]
