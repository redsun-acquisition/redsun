from __future__ import annotations

import asyncio
import threading
import time
from typing import TYPE_CHECKING

import bluesky.plan_stubs as bps
import pytest
from bluesky.utils import RunEngineInterrupted

import redsun.engine.plan_stubs as rps
from redsun.engine.actions import ActionManager, ActionState, PlanAction, SRLatch

if TYPE_CHECKING:
    from collections.abc import Callable

    from bluesky.utils import Msg, MsgGenerator

    from redsun.engine import RunEngine

SNAP = PlanAction(name="snap")
STREAM = PlanAction(name="stream", toggle_states=("Start", "Stop"))


@pytest.fixture
def actions() -> ActionManager:
    return ActionManager()


@pytest.fixture
def seen(actions: ActionManager) -> list[tuple[str, str]]:
    """Return a list gaining every ``(name, state)`` that *actions* reports."""
    reported: list[tuple[str, str]] = []
    actions.sig_changed.connect(lambda name, state: reported.append((name, state)))
    return reported


def _polls(engine: RunEngine) -> list[Msg]:
    """Return a list gaining every poll for an action that *engine* runs.

    A second poll says the first found nothing asked for.
    """
    polls: list[Msg] = []

    def on_message(msg: Msg) -> None:
        if msg.command == "wait_for_actions":
            polls.append(msg)

    engine.msg_hook = on_message  # type: ignore[assignment]
    return polls


async def test_srlatch_lifecycle() -> None:
    latch = SRLatch()
    assert not latch.is_set()
    await latch.wait_for_reset()  # immediate: already reset

    waiter = asyncio.create_task(latch.wait_for_set())
    await asyncio.sleep(0)  # park the waiter
    latch.set()
    latch.set()  # no-op when already set
    await asyncio.wait_for(waiter, timeout=1)
    assert latch.is_set()
    await latch.wait_for_set()  # immediate: already set

    waiter = asyncio.create_task(latch.wait_for_reset())
    await asyncio.sleep(0)
    latch.reset()
    latch.reset()  # no-op when already reset
    await asyncio.wait_for(waiter, timeout=1)
    assert not latch.is_set()


def test_a_latch_set_from_another_thread_wakes_the_plan(RE: RunEngine) -> None:
    """The set is forwarded to the latch's loop, so a 5 s poll is not waited out."""
    latch = SRLatch()
    started = threading.Event()
    RE.msg_hook = lambda msg: started.set()  # type: ignore[assignment]

    future = RE(rps.wait_for_actions({"go": latch}, poll_interval=5.0))
    assert started.wait(5)
    time.sleep(0.1)
    began = time.monotonic()
    latch.set()

    future.result(timeout=5)
    assert time.monotonic() - began < 1.0


def test_a_clicked_and_a_pressed_action_run_from_offer_to_done(
    RE: RunEngine,
    actions: ActionManager,
    seen: list[tuple[str, str]],
    wait_until: Callable[..., bool],
) -> None:
    """A request is reported before the plan reports what it did with it."""

    def plan() -> MsgGenerator[None]:
        name = yield from actions.wait(SNAP, STREAM)
        yield from bps.null()
        actions.done(name)
        name = yield from actions.wait(SNAP, STREAM)
        yield from actions.wait_released(STREAM)
        actions.done(name)

    future = RE(plan())
    assert wait_until(lambda: seen.count(("stream", ActionState.OFFERED)) == 1)
    actions.request("snap")
    assert wait_until(lambda: seen.count(("stream", ActionState.OFFERED)) == 2)
    actions.request("stream")
    assert wait_until(lambda: ("stream", ActionState.RUNNING) in seen)
    actions.request("stream", False)
    future.result(timeout=10)

    assert seen == [
        ("snap", ActionState.OFFERED),
        ("stream", ActionState.OFFERED),
        ("snap", ActionState.REQUESTED),
        ("stream", ActionState.WITHDRAWN),
        ("snap", ActionState.RUNNING),
        ("snap", ActionState.DONE),
        ("snap", ActionState.OFFERED),
        ("stream", ActionState.OFFERED),
        ("stream", ActionState.REQUESTED),
        ("snap", ActionState.WITHDRAWN),
        ("stream", ActionState.RUNNING),
        ("stream", ActionState.RELEASED),
        ("stream", ActionState.DONE),
    ]


@pytest.mark.parametrize(
    ("on", "reason"),
    [
        pytest.param(True, "no plan offers it", id="asked-for"),
        pytest.param(False, "it is not running", id="asked-to-end"),
    ],
)
def test_a_request_nothing_answers_is_refused(
    actions: ActionManager,
    seen: list[tuple[str, str]],
    caplog: pytest.LogCaptureFixture,
    on: bool,
    reason: str,
) -> None:
    actions.request("snap", on)

    assert seen == [("snap", ActionState.REFUSED)]
    assert f"PlanAction 'snap' refused: {reason}" in caplog.text


def test_a_request_made_before_a_plan_waits_does_not_fire_later(
    RE: RunEngine,
    actions: ActionManager,
    seen: list[tuple[str, str]],
    wait_until: Callable[..., bool],
) -> None:
    polls = _polls(RE)
    actions.request("snap")

    future = RE(actions.wait(SNAP, poll_interval=0.01))

    assert wait_until(lambda: len(polls) >= 2)
    assert not future.done()
    assert seen == [("snap", ActionState.REFUSED), ("snap", ActionState.OFFERED)]


def test_a_request_one_launch_left_unanswered_does_not_fire_in_the_next(
    RE: RunEngine,
    actions: ActionManager,
    seen: list[tuple[str, str]],
    wait_until: Callable[..., bool],
) -> None:
    polls = _polls(RE)
    first = RE(actions.wait(SNAP, poll_interval=0.01))
    assert wait_until(lambda: len(polls) >= 1)
    RE.stop().result(timeout=10)
    with pytest.raises(RunEngineInterrupted):
        first.result(timeout=10)
    actions.request("snap")
    polls.clear()

    second = RE(actions.wait(SNAP, poll_interval=0.01))

    assert wait_until(lambda: len(polls) >= 2)
    assert not second.done()
    assert ("snap", ActionState.RUNNING) not in seen


def test_stopping_a_plan_that_waits_withdraws_what_it_offered(
    RE: RunEngine,
    actions: ActionManager,
    seen: list[tuple[str, str]],
    wait_until: Callable[..., bool],
) -> None:
    polls = _polls(RE)
    future = RE(actions.wait(SNAP, STREAM))
    assert wait_until(lambda: len(polls) >= 1)

    RE.stop().result(timeout=10)

    with pytest.raises(RunEngineInterrupted):
        future.result(timeout=10)
    assert seen == [
        ("snap", ActionState.OFFERED),
        ("stream", ActionState.OFFERED),
        ("snap", ActionState.WITHDRAWN),
        ("stream", ActionState.WITHDRAWN),
    ]


def test_waiting_on_no_action_is_refused(RE: RunEngine, actions: ActionManager) -> None:
    with pytest.raises(ValueError, match="no actions to wait on"):
        RE(actions.wait()).result(timeout=10)


def test_waiting_for_the_release_of_an_action_that_is_not_running_is_refused(
    RE: RunEngine, actions: ActionManager
) -> None:
    with pytest.raises(ValueError, match="is not running"):
        RE(actions.wait_released(STREAM)).result(timeout=10)
