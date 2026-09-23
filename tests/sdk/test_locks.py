"""Tests for the device locks a plan takes through the run engine."""

from __future__ import annotations

from typing import TYPE_CHECKING

import bluesky.plan_stubs as bps
import pytest
from bluesky.utils import RunEngineInterrupted
from ophyd_async.core import Device

import redsun.engine.plan_stubs as rps

if TYPE_CHECKING:
    from bluesky.utils import MsgGenerator

    from redsun.engine import RunEngine


def test_a_locked_plan_announces_its_devices_until_it_ends(RE: RunEngine) -> None:
    seen: list[frozenset[str]] = []
    RE.sig_locks_changed.connect(seen.append)

    RE(rps.lock_wrapper(bps.null(), Device(name="stage"))).result(timeout=10)

    assert seen == [{"stage"}, frozenset()]


def test_nested_locks_release_on_the_last_unlock(RE: RunEngine) -> None:
    stage, camera = Device(name="stage"), Device(name="camera")
    during: list[frozenset[str]] = []

    def record() -> MsgGenerator[None]:
        during.append(RE.locked)
        yield from bps.null()

    def plan() -> MsgGenerator[None]:
        yield from rps.lock_wrapper(record(), stage, camera)
        yield from record()
        token = yield from rps.lock(camera)
        yield from record()
        yield from rps.unlock(token)

    RE(rps.lock_wrapper(plan(), stage)).result(timeout=10)

    assert during == [{"stage", "camera"}, {"stage"}, {"stage", "camera"}]
    assert RE.locked == frozenset()


def test_a_failing_plan_unlocks(RE: RunEngine) -> None:
    def fail() -> MsgGenerator[None]:
        yield from bps.null()
        raise RuntimeError("the plan failed")

    with pytest.raises(RuntimeError):
        RE(rps.lock_wrapper(fail(), Device(name="stage"))).result(timeout=10)

    assert RE.locked == frozenset()


def test_a_lock_replayed_after_a_rewind_is_released_once(RE: RunEngine) -> None:
    """Resuming a pause replays the lock message the checkpoint cached."""

    def plan() -> MsgGenerator[None]:
        yield from bps.checkpoint()
        yield from rps.lock_wrapper(bps.pause(), Device(name="stage"))

    with pytest.raises(RunEngineInterrupted):
        RE(plan()).result(timeout=10)
    assert RE.locked == {"stage"}

    RE.resume().result(timeout=10)

    assert RE.locked == frozenset()


def test_a_halted_plan_unlocks(RE: RunEngine) -> None:
    """A halt skips the plan's cleanup, so the engine releases what it held."""
    seen: list[frozenset[str]] = []
    RE.sig_locks_changed.connect(seen.append)

    with pytest.raises(RunEngineInterrupted):
        RE(rps.lock_wrapper(bps.pause(), Device(name="stage"))).result(timeout=10)
    RE.halt()

    assert RE.locked == frozenset()
    assert seen == [{"stage"}, frozenset()]
