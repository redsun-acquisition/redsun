"""The log view shows the session's records, filtered by level, and can save them."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pytest

from redsun.log import log_buffer
from redsun.view import ViewPosition
from redsun.view.qt.builtins import LogView

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from qtpy.QtWidgets import QApplication

pytestmark = pytest.mark.qt


@pytest.fixture
def logs() -> Iterator[logging.Logger]:
    buffer = log_buffer()
    buffer.clear()
    yield logging.getLogger("redsun")
    buffer.clear()


@pytest.fixture
def make_view(qapp: QApplication) -> Iterator[Callable[[], LogView]]:
    """Build views and take them down again, detaching each from the buffer."""
    built: list[LogView] = []

    def build() -> LogView:
        view = LogView("logs")
        built.append(view)
        return view

    yield build
    for view in built:
        view.close()


def test_records_logged_before_the_view_existed_are_shown(
    make_view: Callable[[], LogView], logs: logging.Logger
) -> None:
    """A device or presenter logging during build is on screen when the view opens."""
    logs.warning("built before the view")

    view = make_view()

    assert "built before the view" in view._console.toPlainText()


def test_the_view_sits_at_the_bottom(
    make_view: Callable[[], LogView], logs: logging.Logger
) -> None:
    assert make_view().view_position is ViewPosition.BOTTOM


def test_a_later_record_is_appended(
    make_view: Callable[[], LogView], logs: logging.Logger
) -> None:
    view = make_view()

    logs.error("after the view")

    assert "after the view" in view._console.toPlainText()


@pytest.mark.parametrize(
    ("level", "shown", "hidden"),
    [
        (logging.DEBUG, "a debug line", None),
        (logging.INFO, "an info line", "a debug line"),
        (logging.ERROR, "an error line", "a warning line"),
        (logging.CRITICAL, "a critical line", "an error line"),
    ],
)
def test_the_level_buttons_choose_what_is_displayed(
    make_view: Callable[[], LogView],
    logs: logging.Logger,
    level: int,
    shown: str,
    hidden: str | None,
) -> None:
    logs.debug("a debug line")
    logs.info("an info line")
    logs.warning("a warning line")
    logs.error("an error line")
    logs.critical("a critical line")

    view = make_view()
    view.set_level(level)

    text = view._console.toPlainText()
    assert shown in text
    if hidden is not None:
        assert hidden not in text


def test_lowering_the_level_brings_records_back(
    make_view: Callable[[], LogView], logs: logging.Logger
) -> None:
    """Filtering redraws from the buffer, so nothing is lost by raising it."""
    logs.debug("a debug line")
    view = make_view()

    view.set_level(logging.CRITICAL)
    assert "a debug line" not in view._console.toPlainText()

    view.set_level(logging.DEBUG)
    assert "a debug line" in view._console.toPlainText()


def test_clear_empties_the_console_but_not_the_buffer(
    make_view: Callable[[], LogView], logs: logging.Logger
) -> None:
    logs.info("still buffered")
    view = make_view()

    view.clear()

    assert view._console.toPlainText() == ""
    assert [r.getMessage() for r in log_buffer().records] == ["still buffered"]


def test_save_writes_every_record_whatever_is_displayed(
    make_view: Callable[[], LogView], logs: logging.Logger, tmp_path: Path
) -> None:
    logs.debug("a debug line")
    logs.critical("a critical line")
    view = make_view()
    view.set_level(logging.CRITICAL)
    target = tmp_path / "session.log"

    view.save(str(target))

    written = target.read_text(encoding="utf-8")
    assert "a debug line" in written
    assert "a critical line" in written


def test_the_level_selector_follows_the_displayed_level(
    make_view: Callable[[], LogView], logs: logging.Logger
) -> None:
    """Whichever way the level is set, the combo box shows the one in force."""
    view = make_view()
    assert view._level_combo.currentData() == logging.INFO

    view.set_level(logging.ERROR)

    assert view._level_combo.currentData() == logging.ERROR


def test_choosing_a_level_in_the_selector_filters_the_console(
    make_view: Callable[[], LogView], logs: logging.Logger
) -> None:
    logs.info("an info line")
    logs.critical("a critical line")
    view = make_view()

    view._level_combo.setCurrentIndex(view._level_combo.findData(logging.CRITICAL))

    text = view._console.toPlainText()
    assert view.level == logging.CRITICAL
    assert "a critical line" in text
    assert "an info line" not in text
