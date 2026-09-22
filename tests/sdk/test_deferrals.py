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
