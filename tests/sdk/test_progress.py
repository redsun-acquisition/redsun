"""Tests for the progress a plan reports through the run engine."""

from __future__ import annotations

import asyncio
import gc
import math
import threading
import weakref
from typing import TYPE_CHECKING, Any

import bluesky.plan_stubs as bps
import pytest
from bluesky.utils import FailedStatus, IllegalMessageSequence, RunEngineInterrupted
from ophyd_async.core import AsyncStatus, Device, WatchableAsyncStatus, WatcherUpdate

import redsun.engine.plan_stubs as rps

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

    from bluesky.protocols import Status
    from bluesky.utils import MsgGenerator

    from redsun.engine import ProgressState, RunEngine


def record(RE: RunEngine) -> list[tuple[ProgressState, ...]]:
    """Collect every tuple the engine announces on `sig_progress`."""
    seen: list[tuple[ProgressState, ...]] = []
    RE.sig_progress.connect(seen.append)
    return seen


class WatchedMover(Device):
    """A device whose move reports three steps in millimetres."""

    @WatchableAsyncStatus.wrap
    async def set(self, value: float) -> AsyncIterator[WatcherUpdate[float]]:
        for step in (1.0, 2.0, 3.0):
            await asyncio.sleep(0.01)
            yield WatcherUpdate(
                current=step, initial=0.0, target=value, name=self.name, unit="mm"
            )


class PlainMover(Device):
    """A device whose move reports nothing, and fails when asked to reach 99."""

    @AsyncStatus.wrap
    async def set(self, value: float) -> None:
        await asyncio.sleep(0.05)
        if value == 99:
            raise RuntimeError("the move failed")


class SlowMover(Device):
    """A device whose move goes on reporting after its plan has ended."""

    @WatchableAsyncStatus.wrap
    async def set(self, value: float) -> AsyncIterator[WatcherUpdate[float]]:
        yield WatcherUpdate(current=0.0, initial=0.0, target=value, name=self.name)
        await asyncio.sleep(0.3)
        yield WatcherUpdate(current=value, initial=0.0, target=value, name=self.name)


class ThreadedStatus:
    """A status finished by a worker thread, as an `ophyd` status is."""

    def __init__(self) -> None:
        self._done = False
        self._callbacks: list[Callable[[Status], None]] = []

    @property
    def done(self) -> bool:
        """Whether the worker has finished the status."""
        return self._done

    @property
    def success(self) -> bool:
        """Whether the status finished well, which it always does here."""
        return self._done

    def add_callback(self, callback: Callable[[Status], None]) -> None:
        self._callbacks.append(callback)

    def exception(self, timeout: float | None = 0.0) -> BaseException | None:
        return None

    def finish(self) -> None:
        self._done = True
        for callback in self._callbacks:
            callback(self)


def monitored_after_declared() -> MsgGenerator[None]:
    """Follow a status under the name of a scope already open."""
    status = yield from bps.abs_set(PlainMover(name="mover"), 1.0, wait=True)
    yield from rps.declare_progress("move")
    yield from rps.monitor_progress("move", status)


def monitored_under_a_missing_parent() -> MsgGenerator[None]:
    """Follow a status under a scope never declared."""
    status = yield from bps.abs_set(PlainMover(name="mover"), 1.0, wait=True)
    yield from rps.monitor_progress("move", status, parent="missing")


def declared_twice() -> MsgGenerator[None]:
    """Declare one scope twice."""
    yield from rps.declare_progress("series")
    yield from rps.declare_progress("series")


def under_a_missing_parent() -> MsgGenerator[None]:
    """Declare a scope under one never declared."""
    yield from rps.declare_progress("series", parent="missing")


def update_of_none() -> MsgGenerator[None]:
    """Update a scope never declared."""
    yield from rps.update_progress("series", current=1)


def test_a_scope_is_reported_as_it_is_declared_updated_and_finished(
    RE: RunEngine,
) -> None:
    """Report a scope when declared, on each update, and nothing once it finishes."""
    seen = record(RE)

    def plan() -> MsgGenerator[None]:
        yield from rps.declare_progress("series")
        for done in (1, 2):
            yield from rps.update_progress(
                "series", current=done, initial=0, target=4, unit="frames"
            )
        yield from rps.update_progress("series", done=True)
        yield from bps.null()

    RE(plan()).result(timeout=10)

    assert [[(s.name, s.current, s.fraction) for s in scopes] for scopes in seen] == [
        [("series", None, None)],
        [("series", 1.0, 0.25)],
        [("series", 2.0, 0.5)],
        [("series", 4.0, 1.0)],
        [],
    ]


def test_a_nested_scope_follows_its_parent_and_names_it(RE: RunEngine) -> None:
    """List a nested scope after its parent, naming the parent."""
    seen = record(RE)

    def plan() -> MsgGenerator[None]:
        yield from rps.declare_progress("repeats")
        yield from rps.declare_progress("series", parent="repeats")

    RE(plan()).result(timeout=10)

    listed = [[(s.name, s.parent) for s in scopes] for scopes in seen]
    assert listed[-2] == [("repeats", None), ("series", "repeats")]
    assert listed[-1] == []


@pytest.mark.parametrize(
    "plan",
    [
        declared_twice,
        under_a_missing_parent,
        update_of_none,
        monitored_after_declared,
        monitored_under_a_missing_parent,
    ],
    ids=[
        "declared twice",
        "unknown parent",
        "unknown scope",
        "monitored twice",
        "monitored under an unknown parent",
    ],
)
def test_a_scope_used_out_of_order_is_refused(
    RE: RunEngine, plan: Callable[[], MsgGenerator[None]]
) -> None:
    """Refuse a scope declared twice, one under a missing parent, or an update of none."""
    with pytest.raises(IllegalMessageSequence):
        RE(plan()).result(timeout=10)


def test_a_failing_plan_leaves_no_scope(RE: RunEngine) -> None:
    """Announce that no scope is left when a plan fails with one open."""
    seen = record(RE)

    def plan() -> MsgGenerator[None]:
        yield from rps.declare_progress("series")
        raise RuntimeError("the plan failed")

    with pytest.raises(RuntimeError):
        RE(plan()).result(timeout=10)

    assert seen[-1] == ()


def test_a_paused_plan_keeps_its_scope_and_resumes(RE: RunEngine) -> None:
    """Keep a scope through a pause, and resume without declaring it again."""
    seen = record(RE)

    def plan() -> MsgGenerator[None]:
        yield from bps.checkpoint()
        yield from rps.declare_progress("series")
        yield from rps.update_progress("series", current=1, initial=0, target=2)
        yield from bps.pause()
        yield from rps.update_progress("series", current=2, initial=0, target=2)
        yield from rps.update_progress("series", done=True)

    with pytest.raises(RunEngineInterrupted):
        RE(plan()).result(timeout=10)
    assert [s.current for s in seen[-1]] == [1.0]

    RE.resume().result(timeout=10)

    assert [[s.current for s in scopes] for scopes in seen[-3:]] == [[2.0], [2.0], []]


@pytest.mark.parametrize(
    ("update", "expected"),
    [
        ({"fraction": 0.4}, (None, None, None, 0.4)),
        ({"current": 3, "initial": 1, "target": 5}, (3.0, 1.0, 5.0, 0.5)),
        ({"current": 9, "initial": 0, "target": 5}, (9.0, 0.0, 5.0, 1.0)),
        ({"current": 2, "initial": 2, "target": 2}, (2.0, 2.0, 2.0, None)),
        ({"current": 7}, (7.0, None, None, None)),
        ({"current": "seven", "initial": 0, "target": 5}, (None, 0.0, 5.0, None)),
        ({"current": math.nan, "initial": 0, "target": 5}, (None, 0.0, 5.0, None)),
        ({"current": 1, "initial": 0, "target": math.inf}, (1.0, 0.0, None, None)),
        ({"fraction": math.nan}, (None, 0.0, 1.0, None)),
    ],
    ids=[
        "reported",
        "computed",
        "clamped",
        "no span",
        "no end",
        "not a number",
        "nan",
        "infinite",
        "nan fraction",
    ],
)
def test_a_scope_reports_how_far_it_has_got(
    RE: RunEngine,
    update: dict[str, Any],
    expected: tuple[float | None, float | None, float | None, float | None],
) -> None:
    """Take a reported fraction as given, compute one from numbers, else report none."""
    seen = record(RE)

    def plan() -> MsgGenerator[None]:
        yield from rps.declare_progress("series")
        yield from rps.update_progress("series", **update)

    RE(plan()).result(timeout=10)

    state = next(scopes[0] for scopes in reversed(seen) if scopes)
    assert (state.current, state.initial, state.target, state.fraction) == expected


def test_a_negative_precision_is_dropped(RE: RunEngine) -> None:
    """Report no precision when the plan passes a negative one."""
    seen = record(RE)

    def plan() -> MsgGenerator[None]:
        yield from rps.declare_progress("series")
        yield from rps.update_progress(
            "series", current=1, initial=0, target=2, precision=-1
        )

    RE(plan()).result(timeout=10)

    state = next(scopes[0] for scopes in reversed(seen) if scopes)
    assert state.precision is None


def test_opening_and_closing_a_nested_scope_never_reports_nothing(
    RE: RunEngine,
) -> None:
    """Report an empty tuple only once the last scope has finished."""
    seen = record(RE)

    def plan() -> MsgGenerator[None]:
        yield from rps.declare_progress("repeats")
        for repeat in range(2):
            yield from rps.declare_progress("series", parent="repeats")
            yield from rps.update_progress("series", current=1, initial=0, target=1)
            yield from rps.update_progress("series", done=True)
            yield from rps.update_progress(
                "repeats", current=repeat + 1, initial=0, target=2
            )
        yield from rps.update_progress("repeats", done=True)

    RE(plan()).result(timeout=10)

    assert [index for index, scopes in enumerate(seen) if not scopes] == [len(seen) - 1]


def test_a_finished_scope_is_not_kept_while_the_plan_runs_on(RE: RunEngine) -> None:
    """Let go of a finished scope while other scopes of the plan are still open."""
    kept: list[bool] = []

    def plan() -> MsgGenerator[None]:
        yield from rps.declare_progress("repeats")
        scope = yield from rps.declare_progress("series", parent="repeats")
        ref = weakref.ref(scope)
        del scope
        yield from rps.update_progress("series", done=True)
        yield from rps.update_progress("repeats", current=1, initial=0, target=2)
        gc.collect()
        kept.append(ref() is not None)

    RE(plan()).result(timeout=10)

    assert kept == [False]


def test_a_watchable_status_fills_its_scope(RE: RunEngine) -> None:
    """Report each step a watched move takes, under the plan's name, then nothing."""
    seen = record(RE)
    mover = WatchedMover(name="stage")

    def plan() -> MsgGenerator[None]:
        status = yield from bps.abs_set(mover, 3.0, wait=False, group="move")
        yield from rps.monitor_progress("move", status)
        yield from bps.wait(group="move")

    RE(plan()).result(timeout=10)

    reported = [
        scopes[0] for scopes in seen if scopes and scopes[0].current is not None
    ]
    assert [state.current for state in reported] == [1.0, 2.0, 3.0, 3.0]
    assert {state.name for state in reported} == {"move"}
    assert {state.unit for state in reported} == {"mm"}
    assert seen[-1] == ()


def test_a_plain_status_keeps_a_busy_scope_until_done(RE: RunEngine) -> None:
    """Keep a scope with no end while a silent move runs, and drop it after."""
    seen = record(RE)
    shown: list[tuple[ProgressState, ...]] = []

    def plan() -> MsgGenerator[None]:
        status = yield from bps.abs_set(
            PlainMover(name="stage"), 1.0, wait=False, group="move"
        )
        yield from rps.monitor_progress("move", status)
        shown.append(seen[-1])
        yield from bps.wait(group="move")
        shown.append(seen[-1])

    RE(plan()).result(timeout=10)

    moving, moved = shown
    assert [state.name for state in moving] == ["move"]
    assert moving[0].fraction is None
    assert moved == ()


def test_a_failed_status_closes_its_scope(RE: RunEngine) -> None:
    """Drop the scope of a move that fails, and let the plan's wait raise."""
    seen = record(RE)

    shown: list[tuple[ProgressState, ...]] = []

    def plan() -> MsgGenerator[None]:
        status = yield from bps.abs_set(
            PlainMover(name="stage"), 99, wait=False, group="move"
        )
        yield from rps.monitor_progress("move", status)
        try:
            yield from bps.wait(group="move")
        finally:
            shown.append(seen[-1])

    with pytest.raises(FailedStatus):
        RE(plan()).result(timeout=10)

    assert shown == [()]


def test_a_status_done_before_it_is_passed_closes_its_scope_at_once(
    RE: RunEngine,
) -> None:
    """Close the scope of a finished status before the plan's next step."""

    def plan() -> MsgGenerator[None]:
        status = yield from bps.abs_set(PlainMover(name="stage"), 1.0, wait=True)
        yield from rps.monitor_progress("move", status)
        yield from rps.declare_progress("move")

    RE(plan()).result(timeout=10)


def test_a_status_outliving_its_plan_brings_no_bar_back(RE: RunEngine) -> None:
    """Report nothing more once the plan has ended, however long its move runs."""
    seen = record(RE)
    finished = threading.Event()

    def plan() -> MsgGenerator[None]:
        status = yield from bps.abs_set(SlowMover(name="stage"), 2.0, wait=False)
        status.add_callback(lambda _: finished.set())
        yield from rps.monitor_progress("move", status)

    RE(plan()).result(timeout=10)
    reported = len(seen)
    assert finished.wait(timeout=5)

    assert seen[-1] == ()
    assert len(seen) == reported


def test_a_status_finished_on_another_thread_reports_on_the_engine_thread(
    RE: RunEngine,
) -> None:
    """Announce every change, a scope finished by a worker included, from the engine's thread."""
    status = ThreadedStatus()
    threads: list[int] = []
    RE.sig_progress.connect(lambda _: threads.append(threading.get_ident()))

    def plan() -> MsgGenerator[None]:
        yield from rps.declare_progress("run")
        yield from rps.monitor_progress("move", status, parent="run")
        worker = threading.Thread(target=status.finish)
        worker.start()
        worker.join()
        yield from bps.sleep(0.05)

    RE(plan()).result(timeout=10)

    async def ident() -> int:
        return threading.get_ident()

    engine = asyncio.run_coroutine_threadsafe(ident(), RE.loop).result(timeout=5)
    assert threads and set(threads) == {engine}


def test_a_paused_monitored_plan_resumes(RE: RunEngine) -> None:
    """Resume a plan paused while it follows a move, without refusing its scope."""
    seen = record(RE)

    def plan() -> MsgGenerator[None]:
        yield from bps.checkpoint()
        status = yield from bps.abs_set(
            WatchedMover(name="stage"), 3.0, wait=False, group="move"
        )
        yield from rps.monitor_progress("move", status)
        yield from bps.pause()
        yield from bps.wait(group="move")

    with pytest.raises(RunEngineInterrupted):
        RE(plan()).result(timeout=10)
    RE.resume().result(timeout=10)

    assert seen[-1] == ()


def test_a_failing_progress_display_leaves_the_move_alone(RE: RunEngine) -> None:
    """Complete a followed move, and free its scope, when a progress display raises."""

    def display(scopes: tuple[ProgressState, ...]) -> None:
        if scopes and scopes[0].current is not None:
            raise RuntimeError("the display failed")

    RE.sig_progress.connect(display)

    def plan() -> MsgGenerator[None]:
        status = yield from bps.abs_set(
            WatchedMover(name="stage"), 3.0, wait=False, group="move"
        )
        yield from rps.monitor_progress("move", status)
        yield from bps.wait(group="move")
        yield from rps.declare_progress("move")

    RE(plan()).result(timeout=10)
