from __future__ import annotations

from time import sleep
from typing import TYPE_CHECKING

import pytest
from bluesky.utils import Msg
from ophyd_async.core import soft_signal_rw

import redsun.engine.plan_stubs as rps
from redsun.aio import run_coro
from redsun.engine import register_bound_command
from redsun.engine.actions import Action, SRLatch

if TYPE_CHECKING:
    from typing import Any

    from bluesky.protocols import Descriptor
    from bluesky.utils import MsgGenerator

    from redsun.engine import RunEngine


def test_wait_for_actions_set_after_several_polls(RE: RunEngine) -> None:
    """The stub polls at `poll_interval` until a latch is set."""
    action = Action(name="go")
    events = action.event_map
    results: list[tuple[str, bool]] = []

    def plan() -> MsgGenerator[None]:
        name, latch = yield from rps.wait_for_actions(
            events, poll_interval=0.01, wait_for="set"
        )
        results.append((name, latch.is_set()))

    future = RE(plan())
    # let the stub go through at least one poll that finds nothing first
    sleep(0.1)
    RE.loop.call_soon_threadsafe(events["go"].set)
    future.result(timeout=10)
    assert results == [("go", True)]


def test_wait_for_actions_reset(RE: RunEngine) -> None:
    """wait_for='reset' unblocks when the latch transitions back to reset."""
    action = Action(name="go")
    events = action.event_map
    results: list[str] = []

    def plan() -> MsgGenerator[None]:
        name, _ = yield from rps.wait_for_actions(
            events, poll_interval=0.01, wait_for="set"
        )
        results.append(f"set:{name}")
        name, _ = yield from rps.wait_for_actions(
            events, poll_interval=0.01, wait_for="reset"
        )
        results.append(f"reset:{name}")

    future = RE(plan())
    sleep(0.05)
    RE.loop.call_soon_threadsafe(events["go"].set)
    sleep(0.05)
    RE.loop.call_soon_threadsafe(events["go"].reset)
    future.result(timeout=10)
    assert results == ["set:go", "reset:go"]


def test_wait_for_actions_refuses_an_empty_mapping(RE: RunEngine) -> None:
    with pytest.raises(ValueError, match="no actions to wait on"):
        RE(rps.wait_for_actions({})).result(timeout=10)


@pytest.mark.parametrize("order", [("early", "late"), ("late", "early")])
def test_wait_for_actions_returns_the_latch_set_first(
    RE: RunEngine, order: tuple[str, str]
) -> None:
    latches = {"early": SRLatch(), "late": SRLatch()}
    latches["early"].set()
    # longer than the coarsest step of time.monotonic, 16 ms on Windows
    sleep(0.05)
    latches["late"].set()
    events = {name: latches[name] for name in order}
    results: list[str] = []

    def plan() -> MsgGenerator[None]:
        name, _ = yield from rps.wait_for_actions(events)
        results.append(name)

    RE(plan()).result(timeout=10)
    assert results == ["early"]


@pytest.mark.parametrize("order", [("a", "b"), ("b", "a")])
def test_wait_for_reset_on_unchanged_latches_returns_the_first_in_the_mapping(
    RE: RunEngine, order: tuple[str, str]
) -> None:
    events = {name: SRLatch() for name in order}
    results: list[str] = []

    def plan() -> MsgGenerator[None]:
        name, _ = yield from rps.wait_for_actions(events, wait_for="reset")
        results.append(name)

    RE(plan()).result(timeout=10)
    assert results == [order[0]]


def test_describe_stub_returns_signal_descriptor(RE: RunEngine) -> None:
    async def _make_signal() -> Any:
        return soft_signal_rw(float, initial_value=1.0, name="pos")

    signal = run_coro(_make_signal())
    out: list[dict[str, Descriptor]] = []

    def plan() -> MsgGenerator[None]:
        descriptor = yield from rps.describe(signal)
        out.append(descriptor)

    RE(plan()).result(timeout=10)
    assert "pos" in out[0]


def test_describe_collect_stub(RE: RunEngine) -> None:
    class _Collectable:
        name: str = "collectable"

        def describe_collect(self) -> dict[str, Descriptor]:
            return {"stream": {"source": "test", "dtype": "number", "shape": []}}

    out: list[dict[str, Any]] = []

    def plan() -> MsgGenerator[None]:
        descriptors = yield from rps.describe_collect(_Collectable())
        out.append(descriptors)

    RE(plan()).result(timeout=10)
    assert out[0] == {"stream": {"source": "test", "dtype": "number", "shape": []}}


def test_register_bound_command(RE: RunEngine) -> None:
    seen: list[str] = []

    async def custom_command(engine: RunEngine, msg: Msg) -> None:
        assert engine is RE
        seen.append(msg.command)

    register_bound_command(RE, custom_command)

    def plan() -> MsgGenerator[None]:
        yield Msg("custom_command", None)

    RE(plan()).result(timeout=10)
    assert seen == ["custom_command"]
