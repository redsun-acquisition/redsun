"""The log view shows the session's records, filtered by level, and can save them."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from qtpy import QtCore, QtGui

from redsun.log import (
    BufferHandler,
    SessionFileHandler,
    add_handler,
    log_buffer,
    remove_handler,
    set_level,
)
from redsun.view.qt import _log_view
from redsun.view.qt._log_view import _ON_DARK, _ON_LIGHT
from redsun.view.qt.builtins import LogView

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from qtpy.QtWidgets import QApplication

pytestmark = pytest.mark.qt


@pytest.fixture
def logs() -> Iterator[logging.Logger]:
    """Yield the ``redsun`` logger at ``DEBUG``, over an emptied buffer."""
    logger = logging.getLogger("redsun")
    buffer = log_buffer()
    buffer.clear()
    level = logger.level
    set_level(logging.DEBUG)
    yield logger
    logger.setLevel(level)
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


@pytest.fixture
def small_buffer(logs: logging.Logger) -> Iterator[BufferHandler]:
    """Swap the session buffer for one holding 50 records."""
    installed = log_buffer()
    small = BufferHandler(capacity=50)
    remove_handler(installed)
    add_handler(small)
    yield small
    remove_handler(small)
    add_handler(installed)


@pytest.fixture
def small_service_buffer(logs: logging.Logger) -> Iterator[BufferHandler]:
    """Swap the session buffer for one holding 10 records of each service."""
    installed = log_buffer()
    small = BufferHandler(service_capacity=10)
    remove_handler(installed)
    add_handler(small)
    yield small
    remove_handler(small)
    add_handler(installed)


def _service(name: str) -> logging.Logger:
    return logging.getLogger(f"redsun.service.{name}")


def _draw_pending(view: LogView) -> None:
    """Draw every waiting batch, one timer tick at a time.

    Ticks are driven directly rather than by running the event loop, which
    would also deliver whatever earlier tests left in psygnal's queue.
    """
    while view._batch_timer.isActive():
        view._draw_batch()


def test_records_logged_before_the_view_existed_are_shown(
    make_view: Callable[[], LogView], logs: logging.Logger
) -> None:
    """A device or presenter logging during build is on screen when the view opens."""
    logs.warning("built before the view")

    view = make_view()

    assert "built before the view" in view._console.toPlainText()


def test_a_later_record_is_drawn_after_the_logging_call(
    make_view: Callable[[], LogView], logs: logging.Logger
) -> None:
    """Logging never waits for the console, which catches up on its next batch."""
    view = make_view()

    logs.error("after the view")

    assert "after the view" not in view._console.toPlainText()
    _draw_pending(view)
    assert "after the view" in view._console.toPlainText()


def test_a_burst_is_drawn_a_batch_at_a_time(
    make_view: Callable[[], LogView],
    small_buffer: BufferHandler,
    logs: logging.Logger,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each tick draws at most a batch, so a burst cannot hold the window."""
    monkeypatch.setattr(_log_view, "_BATCH_SIZE", 10)
    view = make_view()

    for i in range(25):
        logs.info("record %02d", i)
    view._draw_batch()

    text = view._console.toPlainText()
    assert "record 09" in text
    assert "record 10" not in text
    _draw_pending(view)
    assert "record 24" in view._console.toPlainText()


def test_the_console_keeps_no_more_lines_than_the_buffer(
    make_view: Callable[[], LogView],
    small_buffer: BufferHandler,
    logs: logging.Logger,
) -> None:
    """Lines past the buffer's capacity are dropped from the top."""
    view = make_view()

    for burst in range(2):
        for i in range(40):
            logs.info("burst %d record %02d", burst, i)
        _draw_pending(view)

    assert view._console.blockCount() == small_buffer.capacity
    assert "burst 0 record 00" not in view._console.toPlainText()


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


def test_the_services_tab_appears_once_a_service_logs(
    make_view: Callable[[], LogView], logs: logging.Logger
) -> None:
    """A session without services shows only the Application tab."""
    view = make_view()
    assert not view._tabs.isTabVisible(_log_view._SERVICES_TAB)

    _service("cam").warning("frame dropped")
    _draw_pending(view)

    assert view._tabs.isTabVisible(_log_view._SERVICES_TAB)
    assert "frame dropped" in view._service_console.toPlainText()
    assert "frame dropped" not in view._console.toPlainText()


def test_the_service_selector_narrows_the_services_console(
    make_view: Callable[[], LogView], logs: logging.Logger
) -> None:
    _service("cam").warning("from the camera")
    _service("stage").warning("from the stage")
    view = make_view()

    view._service_combo.setCurrentIndex(view._service_combo.findData("stage"))
    _service("cam").warning("later from the camera")
    _service("stage").warning("later from the stage")
    _draw_pending(view)

    text = view._service_console.toPlainText()
    assert view.service == "stage"
    assert "from the stage" in text
    assert "later from the stage" in text
    assert "from the camera" not in text


@pytest.mark.parametrize(
    ("tab", "service", "saved", "left_out"),
    [
        (0, None, ["from the application"], ["from the camera", "from the stage"]),
        (1, "cam", ["from the camera"], ["from the application", "from the stage"]),
        (1, None, ["from the camera", "from the stage"], ["from the application"]),
    ],
    ids=["application", "one-service", "all-services"],
)
def test_save_writes_the_records_of_the_tab_shown(
    make_view: Callable[[], LogView],
    logs: logging.Logger,
    tmp_path: Path,
    tab: int,
    service: str | None,
    saved: list[str],
    left_out: list[str],
) -> None:
    logs.warning("from the application")
    _service("cam").warning("from the camera")
    _service("stage").warning("from the stage")
    view = make_view()
    view._tabs.setCurrentIndex(tab)
    view._service_combo.setCurrentIndex(view._service_combo.findData(service))
    target = tmp_path / "saved.log"

    view.save(str(target))

    written = target.read_text(encoding="utf-8")
    assert {line for line in saved + left_out if line in written} == set(saved)


@pytest.mark.parametrize("shown", ["application", "services"])
def test_clear_empties_only_the_tab_shown(
    make_view: Callable[[], LogView], logs: logging.Logger, shown: str
) -> None:
    """Records still waiting to be drawn are cleared with the tab they belong to."""
    logs.warning("from the application")
    _service("cam").warning("from the camera")
    view = make_view()
    logs.warning("waiting from the application")
    _service("cam").warning("waiting from the camera")
    consoles = {"application": view._console, "services": view._service_console}
    kept = "services" if shown == "application" else "application"
    view._tabs.setCurrentIndex(0 if shown == "application" else _log_view._SERVICES_TAB)

    view.clear()
    _draw_pending(view)

    assert consoles[shown].toPlainText() == ""
    assert consoles[kept].toPlainText().count("from the") == 2


def test_a_burst_from_several_services_is_kept_for_each(
    make_view: Callable[[], LogView], small_service_buffer: BufferHandler
) -> None:
    """The services console and its queue grow with each service that logs."""
    view = make_view()

    for i in range(10):
        _service("cam").warning("cam %02d", i)
    for i in range(10):
        _service("stage").warning("stage %02d", i)
    _draw_pending(view)

    text = view._service_console.toPlainText()
    assert "cam 00" in text
    assert "stage 09" in text


def test_save_copies_the_services_log_file_rather_than_the_buffer(
    make_view: Callable[[], LogView], logs: logging.Logger, tmp_path: Path
) -> None:
    application = SessionFileHandler("saved")
    camera = SessionFileHandler("saved", "cam", application.run)
    add_handler(application)
    add_handler(camera, "cam")
    try:
        _service("cam").warning("logged before the buffer dropped it")
        view = make_view()
        log_buffer().clear()
        view._tabs.setCurrentIndex(_log_view._SERVICES_TAB)
        view._service_combo.setCurrentIndex(view._service_combo.findData("cam"))
        target = tmp_path / "session.log"

        view.save(str(target))
    finally:
        remove_handler(application)
        remove_handler(camera, "cam")
        application.close()
        camera.close()

    assert "logged before the buffer dropped it" in target.read_text(encoding="utf-8")


def test_save_copies_the_session_log_rather_than_the_buffer(
    make_view: Callable[[], LogView], logs: logging.Logger, tmp_path: Path
) -> None:
    """A record the buffer has dropped is still in the saved file."""
    handler = SessionFileHandler("saved")
    add_handler(handler)
    try:
        logs.warning("logged before the buffer dropped it")
        log_buffer().clear()
        target = tmp_path / "session.log"

        make_view().save(str(target))
    finally:
        remove_handler(handler)
        handler.close()

    assert "logged before the buffer dropped it" in target.read_text(encoding="utf-8")


def test_the_folder_button_opens_the_session_log_folder(
    make_view: Callable[[], LogView],
    logs: logging.Logger,
    log_directory: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: list[QtCore.QUrl] = []

    def open_url(url: QtCore.QUrl) -> bool:
        opened.append(url)
        return True

    monkeypatch.setattr(QtGui.QDesktopServices, "openUrl", open_url)
    assert not make_view()._folder_button.isEnabled()

    handler = SessionFileHandler("browsed")
    add_handler(handler)
    try:
        view = make_view()
        assert view._folder_button.isEnabled()
        view._folder_button.click()
    finally:
        remove_handler(handler)
        handler.close()

    assert [Path(url.toLocalFile()) for url in opened] == [
        log_directory / "browsed" / "app"
    ]


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


def _repaint(view: LogView, background: str) -> None:
    """Give the console a *background* and let it react to the new palette."""
    palette = view._console.palette()
    palette.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor(background))
    view._console.setPalette(palette)
    view.changeEvent(QtCore.QEvent(QtCore.QEvent.Type.PaletteChange))


@pytest.mark.parametrize(
    ("background", "expected"),
    [("#ffffff", _ON_LIGHT), ("#1e1e1e", _ON_DARK)],
)
def test_the_colours_follow_the_console_background(
    background: str,
    expected: dict[int, str],
    make_view: Callable[[], LogView],
) -> None:
    """A light console and a dark one need different colours to stay legible."""
    view = make_view()

    _repaint(view, background)

    assert view.colors == expected


def _rendered(view: LogView) -> str:
    """Return the console's rich text, which carries the colour of each record."""
    document = view._console.document()
    assert document is not None
    return document.toHtml()


def test_a_palette_change_redraws_what_is_on_screen(
    make_view: Callable[[], LogView], logs: logging.Logger
) -> None:
    """A record drawn for a light console is repainted for a dark one."""
    view = make_view()
    _repaint(view, "#ffffff")
    logs.error("the detector answered nothing")
    _draw_pending(view)
    assert _ON_LIGHT[logging.ERROR] in _rendered(view)

    _repaint(view, "#1e1e1e")

    html = _rendered(view)
    assert _ON_DARK[logging.ERROR] in html
    assert _ON_LIGHT[logging.ERROR] not in html
