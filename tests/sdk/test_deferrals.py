"""A change asked for during a plan lands between two of its messages."""

from __future__ import annotations

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
        self.future: Future[Any] | None = None

    async def apply(self) -> None:
        self.order.append("applied")
        self.applied.set()

    async def fail(self) -> None:
        self.order.append("failed")
        raise RuntimeError("no such setting")

    def plan(self, pause: float = 0.3) -> MsgGenerator[None]:
        self.order.append("first")
        yield from bps.sleep(pause)
        yield from bps.null()
        self.order.append("second")


@pytest.fixture
def running(
    RE: RunEngine, wait_until: Callable[..., bool]
) -> Callable[[Recorder], None]:
    """Return a function starting a recorder's plan and waiting until it runs."""

    def start(recorder: Recorder) -> None:
        recorder.future = RE(recorder.plan())
        assert wait_until(lambda: RE.state == "running")
        time.sleep(0.05)

    return start


def test_a_change_during_a_plan_lands_between_two_messages(
    RE: RunEngine, running: Callable[[Recorder], None]
) -> None:
    deferrals = Deferrals(RE)
    recorder = Recorder()
    running(recorder)

    deferrals.request(recorder.apply)

    assert not recorder.applied.is_set()
    assert recorder.future is not None
    recorder.future.result(timeout=5)
    assert recorder.order == ["first", "applied", "second"]


def test_a_change_while_no_plan_runs_is_applied_at_once(RE: RunEngine) -> None:
    """The future is done once the change ran on the engine's loop."""
    deferrals = Deferrals(RE)
    recorder = Recorder()

    deferrals.request(recorder.apply).result(timeout=5)

    assert recorder.order == ["applied"]


def test_a_change_asked_for_from_a_loop_does_not_block_it(
    RE: RunEngine, wait_until: Callable[..., bool]
) -> None:
    """An async slot on the shared loop asks too; waiting there would deadlock."""
    deferrals = Deferrals(RE)
    recorder = Recorder()

    async def ask() -> None:
        deferrals.request(recorder.apply)

    run_coro(ask())

    assert wait_until(recorder.applied.is_set, timeout=2.0)


def test_a_change_that_fails_is_logged_and_the_next_still_applied(
    RE: RunEngine,
    running: Callable[[Recorder], None],
    caplog: pytest.LogCaptureFixture,
) -> None:
    deferrals = Deferrals(RE)
    recorder = Recorder()
    running(recorder)

    with caplog.at_level(logging.ERROR, logger="redsun"):
        deferrals.request(recorder.fail)
        deferrals.request(recorder.apply)
        assert recorder.future is not None
        recorder.future.result(timeout=5)

    assert recorder.order == ["first", "failed", "applied", "second"]
    assert "A deferred change failed" in caplog.text


def test_a_change_runs_before_the_next_message_without_replaying_any(
    RE: RunEngine, running: Callable[[Recorder], None]
) -> None:
    """The plan is neither suspended nor rewound: every message runs once."""
    deferrals = Deferrals(RE)
    recorder = Recorder()
    seen: list[str] = []
    RE.msg_hook = lambda msg: seen.append(msg.command)  # type: ignore[assignment]
    running(recorder)

    deferrals.request(recorder.apply)
    assert recorder.future is not None
    recorder.future.result(timeout=5)

    assert recorder.order == ["first", "applied", "second"]
    assert seen.count("sleep") == 1
    assert seen.count("null") == 1


def test_a_change_during_the_last_message_is_applied_when_the_plan_ends(
    RE: RunEngine, wait_until: Callable[..., bool]
) -> None:
    deferrals = Deferrals(RE)
    recorder = Recorder()
    future = RE(bps.sleep(0.3))
    assert wait_until(lambda: RE.state == "running")
    time.sleep(0.05)

    applied = deferrals.request(recorder.apply)
    future.result(timeout=5)

    applied.result(timeout=5)
    assert recorder.order == ["applied"]
