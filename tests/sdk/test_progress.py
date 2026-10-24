"""Tests for the progress a plan reports through the run engine."""

from __future__ import annotations

import asyncio
import gc
import threading
import weakref
from functools import partial
from typing import TYPE_CHECKING, Any, NamedTuple

import bluesky.plan_stubs as bps
import pytest
from bluesky.utils import FailedStatus, IllegalMessageSequence, RunEngineInterrupted
from ophyd_async.core import AsyncStatus, Device, WatchableAsyncStatus, WatcherUpdate

import redsun.engine.plan_stubs as rps
from redsun.aio import run_coro
from tests.sdk.mocks import PlainStatus

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

    from bluesky.utils import MsgGenerator

    from redsun.engine import PlanProgress, RunEngine


class Shown(NamedTuple):
    """A scope as the engine announced it."""

    name: str
    """Name of the scope."""

    parent: str | None
    """Name of the scope it is nested under, or `None`."""

    update: WatcherUpdate[Any] | None
    """Its last update when announced, or `None` before the first."""


def record(RE: RunEngine) -> list[tuple[Shown, ...]]:
    """Collect the scopes of every tuple the engine announces on `sig_progress`."""
    seen: list[tuple[Shown, ...]] = []

    def announced(scopes: tuple[PlanProgress, ...]) -> None:
        seen.append(
            tuple(
                Shown(
                    scope.name,
                    scope.parent.name if scope.parent is not None else None,
                    scope.update,
                )
                for scope in scopes
            )
        )

    RE.sig_progress.connect(announced)
    return seen


def current(shown: Shown) -> Any:
    """Return the `current` of *shown*, or `None` before its first update."""
    return shown.update.current if shown.update is not None else None


def record_update(updates: list[dict[str, Any]], **update: Any) -> None:
    """Keep *update*, the keywords a scope passes its watchers."""
    updates.append(update)


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

    assert [[(s.name, current(s)) for s in scopes] for scopes in seen] == [
        [("series", None)],
        [("series", 1)],
        [("series", 2)],
        [("series", 4)],
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
    """Refuse each use of a scope that breaks the order of declare, follow and update."""
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
    assert [current(s) for s in seen[-1]] == [1]

    RE.resume().result(timeout=10)

    assert [[current(s) for s in scopes] for scopes in seen[-3:]] == [[2], [2], []]


def test_a_fraction_reported_alone_reaches_watchers_alone(RE: RunEngine) -> None:
    """Pass a fraction reported alone to watchers, with no current, initial or target."""
    updates: list[dict[str, Any]] = []

    def plan() -> MsgGenerator[None]:
        scope = yield from rps.declare_progress("series")
        scope.watch(partial(record_update, updates))
        yield from rps.update_progress("series", fraction=0.4)

    RE(plan()).result(timeout=10)

    assert [
        (update["current"], update["initial"], update["target"], update["fraction"])
        for update in updates
    ] == [(None, None, None, 0.4), (None, None, None, 1.0)]


def test_a_watcher_added_late_gets_the_last_update_at_once(RE: RunEngine) -> None:
    """Pass a watcher added after an update that update, under the scope's name and timed."""
    updates: list[dict[str, Any]] = []

    def plan() -> MsgGenerator[None]:
        scope = yield from rps.declare_progress("series")
        yield from rps.update_progress("series", current=1, initial=0, target=2)
        scope.watch(partial(record_update, updates))

    RE(plan()).result(timeout=10)

    first = updates[0]
    assert (first["name"], first["current"], first["target"]) == ("series", 1, 2)
    assert first["time_elapsed"] >= 0


def test_a_value_reaches_watchers_as_reported(RE: RunEngine) -> None:
    """Pass watchers the value the plan reported itself, one that cannot be copied included."""
    lock = threading.Lock()
    updates: list[dict[str, Any]] = []

    def plan() -> MsgGenerator[None]:
        scope = yield from rps.declare_progress("series")
        scope.watch(partial(record_update, updates))
        yield from rps.update_progress("series", current=lock)

    RE(plan()).result(timeout=10)

    assert updates[0]["current"] is lock


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
        scopes[0].update for scopes in seen if scopes and current(scopes[0]) is not None
    ]
    assert [update.current for update in reported if update] == [1.0, 2.0, 3.0, 3.0]
    assert {update.name for update in reported if update} == {"move"}
    assert {update.unit for update in reported if update} == {"mm"}
    assert seen[-1] == ()


def test_a_plain_status_keeps_a_busy_scope_until_done(RE: RunEngine) -> None:
    """Keep a scope with no end while a silent move runs, and drop it after."""
    seen = record(RE)
    shown: list[tuple[Shown, ...]] = []

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
    assert moving == (Shown("move", None, None),)
    assert moved == ()


def test_a_failed_status_closes_its_scope(RE: RunEngine) -> None:
    """Drop the scope of a move that fails, and let the plan's wait raise."""
    seen = record(RE)

    shown: list[tuple[Shown, ...]] = []

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
    run_coro(asyncio.sleep(0))  # whatever the callback queued on the loop has run

    assert seen[-1] == ()
    assert len(seen) == reported


def test_a_status_finished_on_another_thread_reports_on_the_engine_thread(
    RE: RunEngine,
) -> None:
    """Announce every change, a scope finished by a worker included, from the engine's thread."""
    status = PlainStatus(done=False)
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

    def display(scopes: tuple[PlanProgress, ...]) -> None:
        if scopes and scopes[0].update is not None:
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
