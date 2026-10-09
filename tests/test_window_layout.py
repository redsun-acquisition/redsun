"""Tests for the window layout a session declares, in its class or its file."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

import pytest

from redsun import (
    AsView,
    BuildError,
    Column,
    ConfigurationError,
    Frontend,
    Placement,
    Row,
    Session,
    Tabs,
    WindowLayout,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from redsun.testing import BuildSession


@dataclass(frozen=True)
class Spot(Placement):
    """A placement naming a region of the toy window, and a group in it."""

    region: str
    group: str | None = None


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


class Card:
    """A view on the left, which fails to build when asked to."""

    placement: Placement = Spot("left")

    def __init__(self, name: str, fail: bool = False) -> None:
        if fail:
            raise RuntimeError("no detector attached")
        self.name = name


class ShelfApp(Session):
    """Two cards on a shelf, laid out by its class."""

    frontend = Shelf
    config: ClassVar[dict[str, Any]] = {"session": "shelf"}

    a: AsView[Card]
    b: AsView[Card]

    def window_layout(self) -> WindowLayout | None:
        return WindowLayout(regions={"left": Tabs("a", "b")})


class PlainShelfApp(Session):
    """Two cards on a shelf, with no layout of its own."""

    frontend = Shelf
    config: ClassVar[dict[str, Any]] = {"session": "plain-shelf"}

    a: AsView[Card]
    b: AsView[Card]


class FourCardsApp(Session):
    """Four cards on a shelf, with no layout of its own."""

    frontend = Shelf
    config: ClassVar[dict[str, Any]] = {"session": "four-cards"}

    a: AsView[Card]
    b: AsView[Card]
    c: AsView[Card]
    d: AsView[Card]


class NoRegionsApp(Session):
    """A session on a frontend with no regions, declaring a layout anyway."""

    config: ClassVar[dict[str, Any]] = {"session": "no-regions"}

    a: AsView[Card]

    def window_layout(self) -> WindowLayout | None:
        return WindowLayout(regions={"left": "a"})


def test_a_session_file_layout_replaces_the_class_one(build: BuildSession) -> None:
    """Take the file's layout, whole, over the one the class returns."""
    app = build(ShelfApp, {"layout": {"regions": {"left": {"column": ["b", "a"]}}}})

    assert app.resolve_layout().regions == {"left": Column("b", "a")}


def test_a_later_file_layer_replaces_the_layout_whole(build: BuildSession) -> None:
    """Take a later layer's layout whole rather than merging its regions into an earlier one."""
    app = build(
        PlainShelfApp,
        [
            {"layout": {"regions": {"left": "a", "center": "b"}}},
            {"layout": {"regions": {"left": "b"}}},
        ],
    )

    assert app.resolve_layout().regions == {"left": Column("b", "a")}


def test_the_file_and_class_forms_build_equal_layouts(build: BuildSession) -> None:
    """Read a file layout into the same objects the class form builds."""
    expected = WindowLayout(
        regions={
            "left": Column(Row("a", "b", sizes=[1, 2]), Tabs("c", "d", current="d"))
        },
        sizes={"left": 0.3},
        hidden=("c",),
    )
    file = {
        "regions": {
            "left": {
                "column": [
                    {"row": ["a", "b"], "sizes": [1, 2]},
                    {"tabs": ["c", "d"], "current": "d"},
                ]
            }
        },
        "sizes": {"left": 0.3},
        "hidden": ["c"],
    }

    app = build(FourCardsApp, {"layout": file})

    assert app.resolve_layout() == expected


def test_a_file_layout_lists_every_problem(build: BuildSession) -> None:
    """Refuse a file layout naming each wrong node, an unknown key among them."""
    layout = {
        "regions": {
            "left": {"row": [], "sizes": [1]},
            "center": {"tabs": ["a"], "current": "z"},
            "top": {"column": ["a"], "rows": 1},
        }
    }

    with pytest.raises(ConfigurationError) as caught:
        build(PlainShelfApp, {"layout": layout})

    message = str(caught.value)
    assert "holds nothing" in message
    assert "not one of its tabs" in message
    assert "rows" in message


@pytest.mark.parametrize(
    ("session", "config", "problem"),
    [
        (NoRegionsApp, None, r"NoRegionsApp\.window_layout\(\)"),
        (PlainShelfApp, {"layout": {"regions": {"attic": "a"}}}, "no region 'attic'"),
    ],
)
def test_a_layout_the_frontend_cannot_show_is_refused(
    build: BuildSession,
    session: type[Session],
    config: dict[str, Any] | None,
    problem: str,
) -> None:
    """Refuse a layout before anything is built, naming where it was declared or what is wrong."""
    with pytest.raises(ConfigurationError, match=problem):
        build(session, config)


def test_a_name_no_view_answers_to_is_logged_and_left_out(
    build: BuildSession, caplog: pytest.LogCaptureFixture
) -> None:
    """Log a layout name no view answers to, and leave it out."""
    app = build(
        PlainShelfApp, {"layout": {"regions": {"left": {"tabs": ["a", "ghost"]}}}}
    )
    caplog.set_level(logging.WARNING, logger="redsun")

    layout = app.resolve_layout()

    assert layout.regions["left"] == Column(Tabs("a"), "b")
    assert "'ghost'" in caplog.text


def test_a_strict_session_refuses_a_name_no_view_answers_to(
    build: BuildSession,
) -> None:
    """Raise when a strict session's layout names a view it does not have."""
    app = build(
        PlainShelfApp, {"strict": True, "layout": {"regions": {"left": "ghost"}}}
    )

    with pytest.raises(BuildError, match="'ghost'"):
        app.resolve_layout()


def test_a_view_that_fails_keeps_its_place(build: BuildSession) -> None:
    """Resolve the same layout when a view fails to build as when it builds."""
    built = build(ShelfApp).resolve_layout()

    failed = build(ShelfApp, {"views": {"a": {"fail": True}}}).resolve_layout()

    assert failed == built


def test_a_file_layout_is_written_back(build: BuildSession) -> None:
    """Write a file's layout section into the configuration the session serializes."""
    layout = {"regions": {"left": {"tabs": ["b", "a"]}}, "sizes": {"left": 0.2}}
    app = build(PlainShelfApp, {"layout": layout})

    assert app.serialize()["layout"] == layout
