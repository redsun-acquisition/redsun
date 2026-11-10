"""Tests for the future a pool returns."""

from __future__ import annotations

import concurrent.futures
import logging
import re
import threading
import weakref

import pytest
from psygnal import emit_queued

from redsun.compute import Future
from redsun.compute._future import PRE_START, Delivery
from redsun.ports import slot
from tests.sdk.helpers import automatic_collection


def handler(value: int) -> None:
    """Do nothing with the result."""


def pump_until(stop: threading.Event) -> None:
    """Deliver queued callbacks on this thread every 10 ms until *stop* is set."""
    while not stop.wait(0.01):
        emit_queued()


class Receiver:
    """Records the thread its marked method runs on."""

    def __init__(self) -> None:
        self.threads: list[threading.Thread] = []
        self.taken = threading.Event()
        self.values: list[int] = []

    def keep(self, value: int) -> None:
        """Record the result."""
        self.values.append(value)

    @slot(thread="current")
    def take(self, value: int) -> None:
        """Record the calling thread."""
        self.threads.append(threading.current_thread())
        self.taken.set()


def test_then_hands_the_result_over_at_once_without_a_session() -> None:
    """Call on_result in the finishing thread when no delivery thread is set."""
    future: Future[int] = Future()
    got: list[int] = []
    future.then(got.append)
    future.set_result(3)
    assert got == [3]


def test_then_sends_a_failure_to_on_error() -> None:
    """Pass the exception of a failed call to on_error."""
    future: Future[int] = Future()
    errors: list[BaseException] = []
    future.then(lambda _: None, errors.append)
    error = ValueError("bad")
    future.set_exception(error)
    assert errors == [error]


def test_an_unhandled_failure_is_logged_once_as_text(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Log a failure with no on_error once, naming the callback, without exc_info."""
    future: Future[int] = Future()
    future.then(handler)
    future.set_exception(ValueError("bad"))
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert "handler" in errors[0].getMessage() and "bad" in errors[0].getMessage()
    assert errors[0].exc_info is None and errors[0].args == ()


def test_a_cancelled_call_is_logged_at_debug_only(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Log a cancelled call at debug level and call neither callback."""
    caplog.set_level(logging.DEBUG, logger="redsun")
    future: Future[int] = Future()
    called: list[object] = []
    future.then(called.append, called.append)
    future.cancel()
    assert called == []
    assert [r.levelno for r in caplog.records] == [logging.DEBUG]


def test_then_drops_the_result_of_a_released_owner() -> None:
    """Skip both callbacks once the owner is gone."""
    future: Future[int] = Future()
    future._bind("owner", None, lambda: True)
    got: list[int] = []
    future.then(got.append)
    future.set_result(1)
    assert got == []


def test_then_queues_for_the_main_thread() -> None:
    """Deliver on the main thread when the delivery names it, once it calls emit_queued."""
    future: Future[str] = Future()
    future._bind("owner", Delivery("main", None), lambda: False)
    got: list[str] = []
    future.then(lambda v: got.append(threading.current_thread().name))
    worker = threading.Thread(target=future.set_result, args=("x",))
    worker.start()
    worker.join()
    assert got == []
    emit_queued()
    assert got == [threading.main_thread().name]


def test_a_delivered_result_frees_its_owner_without_a_collection() -> None:
    """Free the object a queued callback belongs to once the queue drains."""
    with automatic_collection(False):
        owner = Receiver()
        future: Future[int] = Future()
        future._bind("owner", Delivery("main", None), lambda: False)
        future.then(owner.keep)
        future.set_result(1)
        emit_queued()
        assert owner.values == [1]
        ref = weakref.ref(owner)
        del owner, future
        assert ref() is None


def test_a_slot_marker_on_the_callback_wins() -> None:
    """Deliver on the session's thread when the callback's marker says current."""
    receiver = Receiver()
    stop = threading.Event()
    home = threading.Thread(target=pump_until, args=(stop,))
    home.start()
    future: Future[int] = Future()
    future._bind("owner", Delivery(None, home), lambda: False)
    future.then(receiver.take)
    future.set_result(1)
    receiver.taken.wait(timeout=5)
    stop.set()
    home.join()
    assert receiver.threads == [home]


def test_result_before_start_raises() -> None:
    """Refuse result() without a timeout while queued before start, and time out with one."""
    future: Future[int] = Future()
    future._mark_queued(True)
    with pytest.raises(RuntimeError, match=re.escape(PRE_START)):
        future.result()
    with pytest.raises(RuntimeError, match=re.escape(PRE_START)):
        future.exception()
    with pytest.raises(TimeoutError):
        future.result(timeout=0.01)


def test_a_slot_marker_wins_over_a_delivery_thread() -> None:
    """Deliver on the session's thread when the marker says current, whatever the delivery names."""
    receiver = Receiver()
    stop = threading.Event()
    home = threading.Thread(target=pump_until, args=(stop,))
    home.start()
    future: Future[int] = Future()
    future._bind("owner", Delivery("main", home), lambda: False)
    future.then(receiver.take)
    future.set_result(1)
    receiver.taken.wait(timeout=5)
    stop.set()
    home.join()
    assert receiver.threads == [home]


def test_a_raising_callback_is_logged_and_not_propagated(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Log an exception raised by on_result at error level instead of raising it."""

    def explode(value: int) -> None:
        raise ValueError("boom")

    future: Future[int] = Future()
    future.then(explode)
    future.set_result(1)
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1
    assert "explode" in errors[0].getMessage() and "boom" in errors[0].getMessage()
    assert errors[0].exc_info is None and errors[0].args == ()


def test_a_cancelled_queued_future_raises_cancelled_error() -> None:
    """Raise CancelledError, not the pre-start error, from result() once cancelled."""
    future: Future[int] = Future()
    future._mark_queued(True)
    future.cancel()
    with pytest.raises(concurrent.futures.CancelledError):
        future.result()
