"""Tests for the progress a plan reports through the run engine."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import bluesky.plan_stubs as bps
import pytest
from bluesky.utils import IllegalMessageSequence, RunEngineInterrupted

import redsun.engine.plan_stubs as rps

if TYPE_CHECKING:
    from collections.abc import Callable

    from bluesky.utils import MsgGenerator

    from redsun.engine import ProgressState, RunEngine


def record(RE: RunEngine) -> list[tuple[ProgressState, ...]]:
    """Collect every tuple the engine announces on `sig_progress`."""
    seen: list[tuple[ProgressState, ...]] = []
    RE.sig_progress.connect(seen.append)
    return seen


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
    [declared_twice, under_a_missing_parent, update_of_none],
    ids=["declared twice", "unknown parent", "unknown scope"],
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
    ],
    ids=["reported", "computed", "clamped", "no span", "no end", "not a number"],
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
