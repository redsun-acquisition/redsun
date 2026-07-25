from __future__ import annotations

import asyncio

from redsun.engine.actions import Action, ContinousPlan, SRLatch, continous


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


def test_continous_decorator_bare_form() -> None:
    @continous
    def plan() -> None: ...

    assert plan.__togglable__ is True
    assert plan.__pausable__ is False
    assert isinstance(plan, ContinousPlan)


def test_continous_decorator_with_arguments() -> None:
    @continous(togglable=False, pausable=True)
    def plan() -> None: ...

    assert plan.__togglable__ is False
    assert plan.__pausable__ is True


async def test_action_event_map_is_lazy_and_stable() -> None:
    action = Action(name="scan", description="a scan", togglable=True)
    first = action.event_map
    assert list(first.keys()) == ["scan"]
    # the latch is created once and reused
    assert action.event_map["scan"] is first["scan"]
    assert action.toggle_states == ("On", "Off")
