"""Tests for the record of running calls and the GIL watchdog."""

from __future__ import annotations

import logging
import sys
import threading
import time
from functools import partial
from typing import TYPE_CHECKING

import pytest

from redsun.compute import ThreadPool
from redsun.compute._watchdog import Watchdog, running

if TYPE_CHECKING:
    from collections.abc import Generator


def spin_in_python(seconds: float) -> None:
    """Loop in pure Python, holding the GIL, until *seconds* have passed."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        pass


def what_runs() -> dict[str, str]:
    """Return what the pool lists as running, from inside a call."""
    return running()


def thread_name() -> str:
    """Return the name of the thread running the call."""
    return threading.current_thread().name


def explode() -> None:
    """Raise."""
    raise RuntimeError("boom")


@pytest.fixture
def long_switch_interval() -> Generator[None, None, None]:
    """Let a thread holding the GIL keep it for 0.2 s."""
    found = sys.getswitchinterval()
    sys.setswitchinterval(0.2)
    try:
        yield
    finally:
        sys.setswitchinterval(found)


@pytest.fixture(autouse=True)
def warnings_logged(caplog: pytest.LogCaptureFixture) -> None:
    """Capture the warnings of the `redsun` logger."""
    caplog.set_level(logging.WARNING, logger="redsun")


def test_running_lists_a_call_only_while_it_runs() -> None:
    """List the function in its thread while it runs, and nothing after it returns or fails."""
    with ThreadPool(1) as pool:
        inside = pool.submit(what_runs).result(timeout=5)
        worker = pool.submit(thread_name).result(timeout=5)
        failing = pool.submit(explode)
        with pytest.raises(RuntimeError):
            failing.result(timeout=5)
    assert inside == {worker: f"{__name__}.what_runs"}
    assert worker not in running()


def test_running_names_the_submitting_thread_for_an_inline_pool() -> None:
    """Record an inline call under the name of the thread that submitted it."""
    name = threading.current_thread().name
    with ThreadPool(0) as pool:
        inside = pool.submit(what_runs).result()
    assert inside[name] == f"{__name__}.what_runs"
    assert name not in running()


def test_running_looks_through_a_partial() -> None:
    """Name the function a `functools.partial` wraps."""
    with ThreadPool(0) as pool:
        inside = pool.submit(partial(what_runs)).result()
    assert list(inside.values()) == [f"{__name__}.what_runs"]


def test_interleaved_calls_on_same_named_threads_leave_no_entry() -> None:
    """Leave nothing listed when calls of two pools whose threads share a name overlap."""
    a_started = threading.Event()
    b_started = threading.Event()

    def first() -> str:
        a_started.set()
        b_started.wait(5)
        return thread_name()

    def second() -> str:
        b_started.set()
        a_done.result(timeout=5)
        return thread_name()

    with ThreadPool(1) as one, ThreadPool(1) as other:
        a_done = one.submit(first)
        assert a_started.wait(5)
        b_done = other.submit(second)
        names = {a_done.result(timeout=5), b_done.result(timeout=5)}
    assert len(names) == 1
    assert names.isdisjoint(running())


@pytest.mark.usefixtures("long_switch_interval")
def test_the_watchdog_names_a_call_holding_the_gil(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Warn once with the function's name when a pool call holds the GIL past the limit."""
    watchdog = Watchdog(period=0.01, limit=0.05)
    watchdog.start()
    with ThreadPool(1) as pool:
        pool.submit(spin_in_python, 0.5).result(timeout=5)
        pool.submit(spin_in_python, 0.5).result(timeout=5)
    watchdog.stop()
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "spin_in_python" in warnings[0].getMessage()
    assert "may hold the GIL" in warnings[0].getMessage()
    assert warnings[0].name == "redsun.compute"


def test_the_watchdog_is_quiet_for_calls_releasing_the_gil(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Stay quiet while a pool call sleeps, which releases the GIL."""
    watchdog = Watchdog(period=0.01, limit=0.15)
    watchdog.start()
    with ThreadPool(1) as pool:
        pool.submit(time.sleep, 0.3).result(timeout=5)
    watchdog.stop()
    assert not [r for r in caplog.records if r.levelno == logging.WARNING]


def test_stop_ends_the_thread_and_a_watchdog_never_started_stops() -> None:
    """Join the watchdog thread on stop, and let a watchdog that never started stop."""
    Watchdog().stop()
    watchdog = Watchdog(period=0.01)
    watchdog.start()
    assert any(t.name == "redsun-watchdog" for t in threading.enumerate())
    watchdog.stop()
    assert not any(t.name == "redsun-watchdog" for t in threading.enumerate())
