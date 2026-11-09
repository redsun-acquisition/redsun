from __future__ import annotations

import threading
from typing import TYPE_CHECKING

import pytest
from psygnal import emit_queued

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
    """Log a failed call once and leave the callback uncalled."""
    got: list[int] = []
    deliver(ThreadExecutor(1).submit(int, "x"), got.append)
    assert wait_until(lambda: "ValueError" in caplog.text)
    assert got == []


def test_deliver_queues_for_the_main_thread_while_a_frontend_drains(
    monkeypatch: pytest.MonkeyPatch, wait_until: Callable[..., bool]
) -> None:
    """Hold the callback until the main thread drains the queue, then call it there."""
    monkeypatch.setattr("redsun.compute._deliver.DRAINERS", {object()})
    ran_on: list[threading.Thread] = []

    def callback(value: int) -> None:
        ran_on.append(threading.current_thread())

    deliver(ThreadExecutor(1).submit(pow, 2, 3), callback)

    def drained() -> bool:
        emit_queued()
        return bool(ran_on)

    assert wait_until(drained)
    assert ran_on == [threading.main_thread()]
