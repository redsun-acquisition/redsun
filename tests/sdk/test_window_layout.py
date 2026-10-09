"""Tests for the window layout tree, how it resolves and what a frontend accepts."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from redsun import Column, Row, Tabs, WindowLayout

if TYPE_CHECKING:
    from collections.abc import Callable

BASE = WindowLayout(
    regions={"left": Column("a", Tabs("b", "c"), sizes=(1, 2))},
    sizes={"left": 0.25},
    hidden=["d"],
)


def test_a_layout_lists_every_problem_at_once() -> None:
    """Refuse a layout naming a view twice and a region share outside (0, 1), naming both."""
    with pytest.raises(ValueError) as caught:
        WindowLayout(
            regions={"left": Tabs("a", "b"), "right": Column("b", "a")},
            sizes={"left": 1.5},
        )

    assert "'a', 'b'" in str(caught.value)
    assert "between 0 and 1" in str(caught.value)


@pytest.mark.parametrize(
    ("build", "problem"),
    [
        (lambda: Row(), "holds nothing"),
        (lambda: Row("a", "b", sizes=(1,)), "2 children but 1 sizes"),
        (lambda: Column("a", sizes=(0,)), "not positive"),
        (lambda: Tabs(), "holds nothing"),
        (lambda: Tabs("a", current="b"), "not one of its tabs"),
    ],
)
def test_a_node_refuses_what_it_cannot_hold(
    build: Callable[[], object], problem: str
) -> None:
    """Refuse an empty node, sizes that do not fit its children, and a current tab it lacks."""
    with pytest.raises(ValueError, match=problem):
        build()


def test_a_hidden_name_the_layout_does_not_place_is_accepted() -> None:
    """Accept a hidden view the layout leaves to the view's own placement."""
    WindowLayout(hidden=["webcam"])


@pytest.mark.parametrize(
    "changed",
    [
        WindowLayout(
            regions={"left": Column("a", Tabs("b", "c"), sizes=(1, 3))},
            sizes={"left": 0.25},
            hidden=["d"],
        ),
        WindowLayout(
            regions={"left": Column("a", Tabs("b", "c", current="c"), sizes=(1, 2))},
            sizes={"left": 0.25},
            hidden=["d"],
        ),
        WindowLayout(
            regions={"left": Column("a", Tabs("b", "c"), sizes=(1, 2))},
            sizes={"left": 0.3},
            hidden=["d"],
        ),
        WindowLayout(
            regions={"left": Column("a", Tabs("b", "c"), sizes=(1, 2))},
            sizes={"left": 0.25},
        ),
        WindowLayout(
            regions={"left": Column(Tabs("b", "c"), "a", sizes=(2, 1))},
            sizes={"left": 0.25},
            hidden=["d"],
        ),
        WindowLayout(
            regions={"left": Row("a", Tabs("b", "c"), sizes=(1, 2))},
            sizes={"left": 0.25},
            hidden=["d"],
        ),
    ],
)
def test_the_fingerprint_follows_every_change(changed: WindowLayout) -> None:
    """Give equal layouts one fingerprint, and change it with any weight, tab, share, hidden view, order or direction."""
    same = WindowLayout(
        regions={"left": Column("a", Tabs("b", "c"), sizes=(1, 2))},
        sizes={"left": 0.25},
        hidden=("d",),
    )

    assert same.fingerprint() == BASE.fingerprint()
    assert changed.fingerprint() != BASE.fingerprint()
