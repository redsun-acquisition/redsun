"""The log view shows the session's records, filtered by level, and can save them."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from qtpy import QtCore, QtGui
from qtpy.QtWidgets import (
    QApplication,
    QComboBox,
    QDockWidget,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QWidget,
)

from redsun.log import (
    BufferHandler,
    SessionFileHandler,
    add_handler,
    log_buffer,
    remove_handler,
    set_level,
)
from redsun.qt import QtSession
from redsun.view.qt.builtins import LogView
from tests.sdk.view.helpers import child

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from redsun.testing import BuildSession

LIGHT = "#ffffff"
"""A light console background."""

DARK = "#1e1e1e"
"""A dark console background."""

pytestmark = pytest.mark.qt


@pytest.fixture
def logs() -> Iterator[logging.Logger]:
    """Yield the `redsun` logger at `DEBUG`, over an emptied buffer."""
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
    built: list[tuple[LogView, QWidget]] = []

    def build() -> LogView:
        parent = QWidget()
        view = LogView("logs", parent)
        built.append((view, parent))
        return view

    yield build
    # closing the parent sends no closeEvent to its children
    for view, parent in built:
        view.close()
        parent.close()


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


def console(view: LogView) -> QPlainTextEdit:
    """Return the Application tab's console."""
    return child(view, QPlainTextEdit, "console")


def service_console(view: LogView) -> QPlainTextEdit:
    """Return the Services tab's console."""
    return child(view, QPlainTextEdit, "service-console")


def tab_index(view: LogView, label: str) -> int:
    """Return the index of the tab labelled *label*."""
    tabs = child(view, QTabWidget, "tabs")
    return next(i for i in range(tabs.count()) if tabs.tabText(i) == label)


def show_tab(view: LogView, label: str) -> None:
    """Bring the tab labelled *label* to the front."""
    child(view, QTabWidget, "tabs").setCurrentIndex(tab_index(view, label))


def select_service(view: LogView, service: str | None) -> None:
    """Choose *service* in the Services tab's selector, `None` for every service."""
    combo = child(view, QComboBox, "services")
    combo.setCurrentIndex(combo.findData(service))


def service_logger(name: str) -> logging.Logger:
    """Return the logger of the service *name*."""
    return logging.getLogger(f"redsun.service.{name}")


def wait_shown(text: QPlainTextEdit, line: str) -> None:
    """Run the event loop until *line* is on *text*, for at most two seconds."""
    deadline = QtCore.QDeadlineTimer(2000)
    while line not in text.toPlainText() and not deadline.hasExpired():
        QApplication.processEvents()
    assert line in text.toPlainText()


def with_base(palette: QtGui.QPalette, background: str) -> QtGui.QPalette:
    """Return a copy of *palette* whose `Base` colour is *background*."""
    changed = QtGui.QPalette(palette)
    changed.setColor(QtGui.QPalette.ColorRole.Base, QtGui.QColor(background))
    return changed


def rendered(view: LogView) -> str:
    """Return the console's rich text, which carries the colour of each record."""
    document = console(view).document()
    assert document is not None
    return document.toHtml()


def test_records_logged_before_the_view_existed_are_shown(
    make_view: Callable[[], LogView], logs: logging.Logger
) -> None:
    """Show records logged before the view was created."""
    logs.warning("built before the view")

    view = make_view()

    assert "built before the view" in console(view).toPlainText()


def test_a_later_record_is_drawn_after_the_logging_call(
    make_view: Callable[[], LogView], logs: logging.Logger
) -> None:
    """Draw a new record on the next batch, not during the logging call."""
    view = make_view()

    logs.error("after the view")

    assert "after the view" not in console(view).toPlainText()
    wait_shown(console(view), "after the view")


def test_a_burst_filling_the_buffer_is_drawn_over_several_batches(
    make_view: Callable[[], LogView], logs: logging.Logger
) -> None:
    """Draw part of a burst filling the buffer first, and the rest later."""
    view = make_view()
    count = log_buffer().capacity

    for i in range(count):
        logs.info("record %05d", i)
    deadline = QtCore.QDeadlineTimer(2000)
    while not console(view).toPlainText() and not deadline.hasExpired():
        QApplication.processEvents()
    first = console(view).blockCount()
    wait_shown(console(view), f"record {count - 1:05d}")

    assert 0 < first < count
    assert console(view).blockCount() == count


def test_the_console_keeps_no_more_lines_than_the_buffer(
    make_view: Callable[[], LogView],
    small_buffer: BufferHandler,
    logs: logging.Logger,
) -> None:
    """Drop the oldest console lines past the buffer's capacity."""
    view = make_view()

    for burst in range(2):
        for i in range(40):
            logs.info("burst %d record %02d", burst, i)
        wait_shown(console(view), f"burst {burst} record 39")

    assert console(view).blockCount() == small_buffer.capacity
    assert "burst 0 record 00" not in console(view).toPlainText()


@pytest.mark.parametrize(
    ("level", "shown", "hidden"),
    [
        (logging.DEBUG, "a debug line", None),
        (logging.INFO, "an info line", "a debug line"),
        (logging.ERROR, "an error line", "a warning line"),
        (logging.CRITICAL, "a critical line", "an error line"),
    ],
)
def test_the_level_selector_chooses_what_is_displayed(
    make_view: Callable[[], LogView],
    logs: logging.Logger,
    level: int,
    shown: str,
    hidden: str | None,
) -> None:
    """Show records at or above the level selected and hide those below it."""
    logs.debug("a debug line")
    logs.info("an info line")
    logs.warning("a warning line")
    logs.error("an error line")
    logs.critical("a critical line")
    view = make_view()

    combo = child(view, QComboBox, "level")
    combo.setCurrentIndex(combo.findData(level))

    text = console(view).toPlainText()
    assert view.level == level
    assert shown in text
    if hidden is not None:
        assert hidden not in text


def test_lowering_the_level_brings_records_back(
    make_view: Callable[[], LogView], logs: logging.Logger
) -> None:
    """Show again the records a higher level hid once the level is lowered."""
    logs.debug("a debug line")
    view = make_view()

    view.set_level(logging.CRITICAL)
    assert "a debug line" not in console(view).toPlainText()

    view.set_level(logging.DEBUG)
    assert "a debug line" in console(view).toPlainText()


def test_clear_empties_the_console_but_not_the_buffer(
    make_view: Callable[[], LogView], logs: logging.Logger
) -> None:
    """Empty the console on clear and keep the buffered records."""
    logs.info("still buffered")
    view = make_view()

    child(view, QPushButton, "clear").click()

    assert console(view).toPlainText() == ""
    assert [r.getMessage() for r in log_buffer().records] == ["still buffered"]


def test_save_writes_every_record_whatever_is_displayed(
    make_view: Callable[[], LogView], logs: logging.Logger, tmp_path: Path
) -> None:
    """Save every record, including those the level hides."""
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
    """Show the services tab only once a service logs."""
    view = make_view()
    tabs = child(view, QTabWidget, "tabs")
    assert not tabs.isTabVisible(tab_index(view, "Services"))

    service_logger("cam").warning("frame dropped")
    wait_shown(service_console(view), "frame dropped")

    assert tabs.isTabVisible(tab_index(view, "Services"))
    assert "frame dropped" not in console(view).toPlainText()


def test_the_service_selector_narrows_the_services_console(
    make_view: Callable[[], LogView], logs: logging.Logger
) -> None:
    """Show only the selected service's records in the services console."""
    service_logger("cam").warning("from the camera")
    service_logger("stage").warning("from the stage")
    view = make_view()

    select_service(view, "stage")
    service_logger("cam").warning("later from the camera")
    service_logger("stage").warning("later from the stage")
    wait_shown(service_console(view), "later from the stage")

    text = service_console(view).toPlainText()
    assert view.service == "stage"
    assert "from the stage" in text
    assert "from the camera" not in text


@pytest.mark.parametrize(
    ("tab", "service", "saved", "left_out"),
    [
        (
            "Application",
            None,
            ["from the application"],
            ["from the camera", "from the stage"],
        ),
        (
            "Services",
            "cam",
            ["from the camera"],
            ["from the application", "from the stage"],
        ),
        (
            "Services",
            None,
            ["from the camera", "from the stage"],
            ["from the application"],
        ),
    ],
    ids=["application", "one-service", "all-services"],
)
def test_save_writes_the_records_of_the_tab_shown(
    make_view: Callable[[], LogView],
    logs: logging.Logger,
    tmp_path: Path,
    tab: str,
    service: str | None,
    saved: list[str],
    left_out: list[str],
) -> None:
    """Save the records of the tab and service shown."""
    logs.warning("from the application")
    service_logger("cam").warning("from the camera")
    service_logger("stage").warning("from the stage")
    view = make_view()
    show_tab(view, tab)
    select_service(view, service)
    target = tmp_path / "saved.log"

    view.save(str(target))

    written = target.read_text(encoding="utf-8")
    assert {line for line in saved + left_out if line in written} == set(saved)


@pytest.mark.parametrize(
    ("shown", "kept"), [("Application", "Services"), ("Services", "Application")]
)
def test_clear_empties_only_the_tab_shown(
    make_view: Callable[[], LogView], logs: logging.Logger, shown: str, kept: str
) -> None:
    """Clear the shown tab, including its undrawn records, and keep the other."""
    logs.warning("from the application")
    service_logger("cam").warning("from the camera")
    view = make_view()
    logs.warning("waiting from the application")
    service_logger("cam").warning("waiting from the camera")
    consoles = {"Application": console(view), "Services": service_console(view)}
    waiting = {
        "Application": "waiting from the application",
        "Services": "waiting from the camera",
    }
    show_tab(view, shown)

    child(view, QPushButton, "clear").click()
    wait_shown(consoles[kept], waiting[kept])

    assert consoles[shown].toPlainText() == ""
    assert consoles[kept].toPlainText().count("from the") == 2


def test_a_burst_from_several_services_is_kept_for_each(
    make_view: Callable[[], LogView], small_service_buffer: BufferHandler
) -> None:
    """Keep a burst of records from each of several services."""
    view = make_view()

    for i in range(10):
        service_logger("cam").warning("cam %02d", i)
    for i in range(10):
        service_logger("stage").warning("stage %02d", i)
    wait_shown(service_console(view), "stage 09")

    assert "cam 00" in service_console(view).toPlainText()


def test_save_copies_the_services_log_file_rather_than_the_buffer(
    make_view: Callable[[], LogView], logs: logging.Logger, tmp_path: Path
) -> None:
    """Save a service's log file, including records the buffer dropped."""
    application = SessionFileHandler("saved")
    camera = SessionFileHandler("saved", "cam", application.run)
    add_handler(application)
    add_handler(camera, "cam")
    try:
        service_logger("cam").warning("logged before the buffer dropped it")
        view = make_view()
        log_buffer().clear()
        show_tab(view, "Services")
        select_service(view, "cam")
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
    """Save the session log file, including records the buffer dropped."""
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
    """Open the session log folder, and disable the button with no log file."""
    opened: list[QtCore.QUrl] = []

    def open_url(url: QtCore.QUrl) -> bool:
        opened.append(url)
        return True

    monkeypatch.setattr(QtGui.QDesktopServices, "openUrl", open_url)
    assert not child(make_view(), QPushButton, "folder").isEnabled()

    handler = SessionFileHandler("browsed")
    add_handler(handler)
    try:
        folder = child(make_view(), QPushButton, "folder")
        assert folder.isEnabled()
        folder.click()
    finally:
        remove_handler(handler)
        handler.close()

    assert [Path(url.toLocalFile()) for url in opened] == [
        log_directory / "browsed" / "app"
    ]


def test_the_level_selector_follows_the_displayed_level(
    make_view: Callable[[], LogView], logs: logging.Logger
) -> None:
    """Show the level set through `set_level` in the level selector."""
    view = make_view()
    combo = child(view, QComboBox, "level")
    assert combo.currentData() == logging.INFO

    view.set_level(logging.ERROR)

    assert combo.currentData() == logging.ERROR


@pytest.mark.parametrize("background", [LIGHT, DARK])
def test_the_colours_contrast_with_the_console_background(
    make_view: Callable[[], LogView], background: str
) -> None:
    """Pick dark level colours on a light background and light ones on a dark one."""
    view = make_view()

    view.setPalette(with_base(view.palette(), background))

    light_background = QtGui.QColor(background).lightness() >= 128
    assert all(
        (QtGui.QColor(color).lightness() < 128) == light_background
        for color in view.colors.values()
    )


def test_a_palette_change_redraws_what_is_on_screen(
    qapp: QApplication, make_view: Callable[[], LogView], logs: logging.Logger
) -> None:
    """Redraw the shown records in the colours of the application palette applied."""
    original = QtGui.QPalette(qapp.palette())
    try:
        qapp.setPalette(with_base(original, LIGHT))
        view = make_view()
        logs.error("the detector answered nothing")
        wait_shown(console(view), "the detector answered nothing")
        light = view.colors[logging.ERROR]
        assert light in rendered(view)

        qapp.setPalette(with_base(original, DARK))
        qapp.processEvents()

        html = rendered(view)
        assert view.colors[logging.ERROR] in html
        assert light not in html
    finally:
        qapp.setPalette(original)


def test_a_qt_session_docks_the_built_in_view_at_the_bottom(
    qapp: QApplication, build: BuildSession
) -> None:
    """Dock the built-in log view at the bottom of the main window."""
    views = {"logs": {"plugin_name": "redsun", "plugin_id": "logs"}}
    session = build(QtSession.from_config({"session": "lab", "views": views}))

    view = session.views["logs"]
    assert isinstance(view, LogView)
    dock = view.parentWidget()
    assert isinstance(dock, QDockWidget)
    area = session.main_window.dockWidgetArea(dock)
    assert area == QtCore.Qt.DockWidgetArea.BottomDockWidgetArea
