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
    """Return a list gaining every `(name, state)` that *actions* reports."""
    reported: list[tuple[str, str]] = []
    actions.sig_changed.connect(lambda name, state: reported.append((name, state)))
    return reported


async def test_srlatch_lifecycle() -> None:
    """Set and reset an SRLatch, waking whoever waits on each state."""
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
    """Wake a waiting plan at once when its latch is set from another thread."""
    latch = SRLatch()
    started = threading.Event()

    def on_message(msg: Msg) -> None:
        if msg.command == "wait_for_actions":
            started.set()

    RE.msg_hook = on_message  # type: ignore[assignment]

    # The set is forwarded to the latch's loop, so this 5 s poll is not waited out.
    future = RE(rps.wait_for_actions({"go": latch}, poll_interval=5.0))
    assert started.wait(5)
    time.sleep(0.1)  # the hook runs before the message does, let the wait begin
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
    """Report every state change of a clicked and a pressed action, in plan order."""

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
        ("stream", ActionState.IDLE),
        ("snap", ActionState.RUNNING),
        ("snap", ActionState.IDLE),
        ("snap", ActionState.OFFERED),
        ("stream", ActionState.OFFERED),
        ("snap", ActionState.IDLE),
        ("stream", ActionState.RUNNING),
        ("stream", ActionState.IDLE),
    ]


@pytest.mark.parametrize(
    ("on", "reason"),
    [
        pytest.param(True, "no plan offers it", id="asked-for"),
        pytest.param(False, "it is not running", id="asked-to-end"),
    ],
)
def test_a_request_nothing_answers_is_logged_and_changes_no_state(
    actions: ActionManager,
    seen: list[tuple[str, str]],
    caplog: pytest.LogCaptureFixture,
    on: bool,
    reason: str,
) -> None:
    """Log a request to start or end an action nothing answers; change no state."""
    actions.request("snap", on)

    assert seen == []
    assert f"Action 'snap' refused: {reason}" in caplog.text


def test_a_request_made_before_a_plan_waits_does_not_fire_later(
    RE: RunEngine,
    polls: list[Msg],
    actions: ActionManager,
    seen: list[tuple[str, str]],
    wait_until: Callable[..., bool],
) -> None:
    """Ignore a request made before a plan starts waiting for the action."""
    actions.request("snap")

    future = RE(actions.wait(SNAP, poll_interval=0.01))

    assert wait_until(lambda: len(polls) >= 2)
    assert not future.done()
    assert seen == [("snap", ActionState.OFFERED)]


def test_a_request_one_launch_left_unanswered_does_not_fire_in_the_next(
    RE: RunEngine,
    polls: list[Msg],
    actions: ActionManager,
    seen: list[tuple[str, str]],
    wait_until: Callable[..., bool],
) -> None:
    """Discard a request a stopped plan left unanswered, so the next ignores it."""
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


def test_stopping_a_plan_that_waits_puts_what_it_offered_back_to_idle(
    RE: RunEngine,
    polls: list[Msg],
    actions: ActionManager,
    seen: list[tuple[str, str]],
    wait_until: Callable[..., bool],
) -> None:
    """Return offered actions to idle when a waiting plan is stopped."""
    future = RE(actions.wait(SNAP, STREAM))
    assert wait_until(lambda: len(polls) >= 1)

    RE.stop().result(timeout=10)

    with pytest.raises(RunEngineInterrupted):
        future.result(timeout=10)
    assert seen == [
        ("snap", ActionState.OFFERED),
        ("stream", ActionState.OFFERED),
        ("snap", ActionState.IDLE),
        ("stream", ActionState.IDLE),
    ]


def test_waiting_on_no_action_is_refused(RE: RunEngine, actions: ActionManager) -> None:
    """Refuse a wait given no actions."""
    with pytest.raises(ValueError, match="no actions to wait on"):
        RE(actions.wait()).result(timeout=10)


def test_waiting_for_the_release_of_an_action_that_is_not_running_is_refused(
    RE: RunEngine, actions: ActionManager
) -> None:
    """Refuse to wait for the release of an action that is not running."""
    with pytest.raises(ValueError, match="is not running"):
        RE(actions.wait_released(STREAM)).result(timeout=10)
