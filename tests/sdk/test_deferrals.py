"""A change asked for during a plan lands between two of its messages."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from concurrent.futures import Future
from typing import TYPE_CHECKING, Any

import bluesky.plan_stubs as bps
import pytest

from redsun.aio import run_coro
from redsun.engine import Deferrals, RunEngine

if TYPE_CHECKING:
    from collections.abc import Callable

    from bluesky.utils import MsgGenerator


class Recorder:
    """Records what happened in which order, from the plan and from a change."""

    def __init__(self) -> None:
        self.order: list[str] = []
        self.applied = threading.Event()
        self.inside = threading.Event()
        self.gate = asyncio.Event()
        self.future: Future[Any] | None = None

    async def apply(self) -> None:
        self.order.append("applied")
        self.applied.set()

    async def apply_slowly(self) -> None:
        await asyncio.sleep(0.2)
        await self.apply()

    async def fail(self) -> None:
        self.order.append("failed")
        raise RuntimeError("no such setting")

    async def hold(self) -> None:
        self.inside.set()
        await self.gate.wait()
        self.order.append("message end")

    def plan(self) -> MsgGenerator[None]:
        self.order.append("first")
        yield from bps.wait_for([self.hold])
        yield from bps.null()
        self.order.append("second")


@pytest.fixture
def running(RE: RunEngine) -> Callable[[Recorder], None]:
    """Return a function starting a recorder's plan and waiting inside its first message."""

    def start(recorder: Recorder) -> None:
        recorder.future = RE(recorder.plan())
        assert recorder.inside.wait(timeout=5)

    return start


@pytest.fixture
def finish(RE: RunEngine) -> Callable[[Recorder], None]:
    """Return a function ending a recorder's first message and waiting for its plan.

    The gate opens through the engine's loop, after every change requested
    before it has reached that loop.
    """

    def end(recorder: Recorder) -> None:
        RE.loop.call_soon_threadsafe(recorder.gate.set)
        assert recorder.future is not None
        recorder.future.result(timeout=5)

    return end


def test_a_change_during_a_plan_lands_between_two_messages(
    RE: RunEngine,
    running: Callable[[Recorder], None],
    finish: Callable[[Recorder], None],
) -> None:
    """Apply a change requested during a plan between two of its messages."""
    deferrals = Deferrals(RE)
    recorder = Recorder()
    running(recorder)

    deferrals.request(recorder.apply)
    finish(recorder)

    assert recorder.order == ["first", "message end", "applied", "second"]


def test_a_change_while_no_plan_runs_is_applied_at_once(RE: RunEngine) -> None:
    """Apply a change at once when no plan runs, and complete its future."""
    deferrals = Deferrals(RE)
    recorder = Recorder()

    deferrals.request(recorder.apply).result(timeout=5)

    assert recorder.order == ["applied"]


def test_a_change_asked_for_from_a_loop_does_not_block_it(
    RE: RunEngine, wait_until: Callable[..., bool]
) -> None:
    """Accept a change requested from the shared loop without blocking it."""
    deferrals = Deferrals(RE)
    recorder = Recorder()

    async def ask() -> None:
        deferrals.request(recorder.apply)

    run_coro(ask(), timeout=5)

    assert wait_until(recorder.applied.is_set, timeout=2.0)


def test_a_change_that_fails_is_logged_and_the_next_still_applied(
    RE: RunEngine,
    running: Callable[[Recorder], None],
    finish: Callable[[Recorder], None],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Log a failing change and still apply the changes after it."""
    deferrals = Deferrals(RE)
    recorder = Recorder()
    running(recorder)

    with caplog.at_level(logging.ERROR, logger="redsun"):
        deferrals.request(recorder.fail)
        deferrals.request(recorder.apply)
        finish(recorder)

    assert recorder.order == ["first", "message end", "failed", "applied", "second"]
    assert "A deferred change failed" in caplog.text


def test_a_change_runs_before_the_next_message_without_replaying_any(
    RE: RunEngine,
    running: Callable[[Recorder], None],
    finish: Callable[[Recorder], None],
) -> None:
    """Apply a change after the message under way and run no message twice."""
    deferrals = Deferrals(RE)
    recorder = Recorder()
    seen: list[str] = []
    RE.msg_hook = lambda msg: seen.append(msg.command)  # type: ignore[assignment]
    running(recorder)

    deferrals.request(recorder.apply)
    finish(recorder)

    assert recorder.order == ["first", "message end", "applied", "second"]
    assert seen.count("null") == 1


def test_a_change_during_the_last_message_is_applied_before_the_plan_returns(
    RE: RunEngine, wait_until: Callable[..., bool]
) -> None:
    """Apply a change made during the last message before the plan returns."""
    deferrals = Deferrals(RE)
    recorder = Recorder()
    future = RE(bps.sleep(0.3))
    assert wait_until(lambda: RE.state == "running")
    time.sleep(0.05)

    deferrals.request(recorder.apply_slowly)
    future.result(timeout=5)

    assert recorder.order == ["applied"]


def test_a_change_left_by_a_halted_plan_is_applied_once_idle(
    RE: RunEngine, wait_until: Callable[..., bool]
) -> None:
    """Apply a change left pending by a halted plan once the engine is idle."""
    deferrals = Deferrals(RE)
    recorder = Recorder()
    RE(bps.sleep(5))
    assert wait_until(lambda: RE.state == "running")
    time.sleep(0.05)

    applied = deferrals.request(recorder.apply)
    RE.halt().result(timeout=5)

    applied.result(timeout=5)
    assert recorder.order == ["applied"]


def test_a_cancelled_change_is_dropped_and_the_next_still_applied(
    RE: RunEngine,
    running: Callable[[Recorder], None],
    finish: Callable[[Recorder], None],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Drop a change whose request was cancelled, and apply the one queued after it."""
    deferrals = Deferrals(RE)
    recorder = Recorder()
    running(recorder)

    async def dropped() -> None:
        recorder.order.append("dropped")

    deferrals.request(dropped).cancel()
    deferrals.request(recorder.apply)
    finish(recorder)

    assert recorder.order == ["first", "message end", "applied", "second"]
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]
