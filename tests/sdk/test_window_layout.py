"""Tests for the window layout tree, how it resolves and what a frontend accepts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, ClassVar

import pytest

from redsun import Column, Frontend, Placement, Row, Tabs, WindowLayout
from redsun.session._layout import resolved_layout

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping


@dataclass(frozen=True)
class Spot(Placement):
    """A placement naming a region of the toy window, and a group in it."""

    region: str
    group: str | None = None


@dataclass(frozen=True)
class Menu(Placement):
    """A placement outside any region."""


class Shelf(Frontend):
    """A frontend with a column on the left and tabs in the centre."""

    regions: ClassVar[Mapping[str, type[Row | Column | Tabs]]] = {
        "left": Column,
        "center": Tabs,
    }
    hides: ClassVar[bool] = True

    @classmethod
    def region_of(cls, placement: Placement) -> tuple[str, str | None] | None:
        if isinstance(placement, Spot):
            return placement.region, placement.group
        return None


class Flat(Frontend):
    """A frontend with one region, which starts nothing hidden."""

    regions: ClassVar[Mapping[str, type[Row | Column | Tabs]]] = {"left": Column}


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
    WindowLayout(hidden=["camera"])


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


def test_without_a_layout_the_placements_decide() -> None:
    """Stack a region's views in declaration order, tab a group at its first view, tab several central views."""
    placements: dict[str, Placement | None] = {
        "a": Spot("left"),
        "b": Spot("left", group="tools"),
        "c": Spot("left"),
        "d": Spot("left", group="tools"),
        "e": Spot("center"),
        "f": Spot("center"),
        "g": Menu(),
        "h": None,
    }

    layout, dropped = resolved_layout(None, placements, Shelf)

    assert layout.regions == {
        "left": Column("a", Tabs("b", "d"), "c"),
        "center": Tabs("e", "f"),
    }
    assert dropped == []


def test_a_declared_layout_places_the_views_it_names() -> None:
    """Put each named view where the layout says, whatever its placement, and the others after it."""
    declared = WindowLayout(regions={"left": Tabs("x", "y")})
    placements: dict[str, Placement | None] = {
        "x": Spot("center"),
        "y": Spot("left"),
        "z": Spot("left"),
    }

    layout, _ = resolved_layout(declared, placements, Shelf)

    assert layout.regions == {"left": Column(Tabs("x", "y"), "z")}


def test_names_no_view_in_a_region_answers_to_are_dropped() -> None:
    """Drop an unknown name and a view placed outside any region, from the tree, its sizes and hidden."""
    declared = WindowLayout(
        regions={"left": Column("a", "ghost", "m", sizes=(1, 2, 3))},
        hidden=["a", "nobody"],
    )
    placements: dict[str, Placement | None] = {"a": Spot("left"), "m": Menu()}

    layout, dropped = resolved_layout(declared, placements, Shelf)

    assert layout.regions == {"left": Column("a", sizes=(1,))}
    assert layout.hidden == ("a",)
    assert dropped == ["ghost", "m", "nobody"]


def test_a_central_view_left_out_joins_the_declared_tabs() -> None:
    """Add a central view the layout leaves out to the centre's tabs, keeping the tab on top."""
    declared = WindowLayout(regions={"center": Tabs("p", "q", current="q")})
    placements: dict[str, Placement | None] = {
        "p": Spot("center"),
        "q": Spot("center"),
        "r": Spot("center"),
    }

    layout, _ = resolved_layout(declared, placements, Shelf)

    assert layout.regions == {"center": Tabs("p", "q", "r", current="q")}


@pytest.mark.parametrize(
    ("frontend", "layout", "problem"),
    [
        (Frontend, WindowLayout(regions={"left": "a"}), "lays out no window"),
        (Shelf, WindowLayout(regions={"attic": "a"}), "no region 'attic'"),
        (Shelf, WindowLayout(sizes={"attic": 0.5}), "no region 'attic'"),
        (Flat, WindowLayout(hidden=["a"]), "starts no view hidden"),
    ],
)
def test_a_frontend_names_what_it_cannot_show(
    frontend: type[Frontend], layout: WindowLayout, problem: str
) -> None:
    """Refuse any layout on a frontend with no regions, an unknown region, and hidden views it cannot hide."""
    assert any(problem in line for line in frontend.layout_problems(layout))
