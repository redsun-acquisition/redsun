"""Tests for attaching experimental views to a Qt main window."""

from __future__ import annotations

import subprocess
import sys
from typing import TYPE_CHECKING, Any, ClassVar

import pytest
import yaml
from app_model import Action, Application
from app_model.types import MenuRule
from qtpy.QtGui import QAction, QCloseEvent
from qtpy.QtWidgets import (
    QApplication,
    QDockWidget,
    QMainWindow,
    QMenu,
    QTabWidget,
    QToolBar,
    QWidget,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

from redsun.experimental import (
    AppContainer,
    AsPresenter,
    AsView,
    AttachableComponent,
    Placement,
)
from redsun.experimental.containers.qt import (
    Central,
    Dock,
    MenuItem,
    Qt,
    QtAppContainer,
    ToolBarItem,
    attach,
)
from redsun.experimental.containers.qt._container import SAVE_MENU

pytestmark = pytest.mark.qt


class Panel(QWidget):
    placement: Placement = Dock("left")

    def __init__(self, name: str, /) -> None:
        super().__init__()
        self.name = name


class Canvas(QWidget):
    placement: Placement = Central()

    def __init__(self, name: str, /) -> None:
        super().__init__()
        self.name = name


class Other(QWidget):
    placement: Placement = Central()

    def __init__(self, name: str, /) -> None:
        super().__init__()
        self.name = name


class Save(QAction):
    placement: Placement = MenuItem("File")

    def __init__(self, name: str, /) -> None:
        super().__init__(name)
        self.name = name


class Open(QAction):
    placement: Placement = MenuItem("File")

    def __init__(self, name: str, /) -> None:
        super().__init__(name)
        self.name = name


class Acquire(QAction):
    placement: Placement = ToolBarItem("Plans")

    def __init__(self, name: str, /) -> None:
        super().__init__(name)
        self.name = name


class NotAWidget:
    placement: Placement = Dock("left")

    def __init__(self, name: str, /) -> None:
        self.name = name


class QtApp(QtAppContainer):
    __slots__ = ()

    panel: AsView[Panel]
    canvas: AsView[Canvas]
    save: AsView[Save]
    acquire: AsView[Acquire]


def test_the_session_owns_an_application_named_after_it() -> None:
    """Commands, menus and keybindings belong to the session, not the process."""
    app = QtApp()
    with pytest.raises(RuntimeError, match=r"Call build\(\) before"):
        _ = app.model
    app.build()
    try:
        assert app.model is Application.get_app("QtApp")
    finally:
        app.shutdown()
    assert Application.get_app("QtApp") is None


def test_two_sessions_of_one_name_refuse_to_coexist(
    qapp: QApplication,
    build: Callable[..., QtAppContainer],
) -> None:
    """The name is an identity, so a collision is loud rather than shared."""
    build(QtApp)
    with pytest.raises(ValueError, match="already exists"):
        QtApp().build()


def test_the_name_is_free_again_after_shutdown() -> None:
    """A suite building one session repeatedly is the case this serves."""
    for _ in range(3):
        app = QtApp().build()
        assert app.model.name == "QtApp"
        app.shutdown()


@pytest.fixture
def window() -> QMainWindow:
    return QMainWindow()


def test_the_container_builds_its_own_window(
    qapp: QApplication,
    build: Callable[..., QtAppContainer],
) -> None:
    """The base container builds the components; this one arranges them."""
    app = build(QtApp)
    window = app.main_window
    assert window.windowTitle() == "QtApp"
    docks = window.findChildren(QDockWidget)
    assert [_widget(d).objectName() for d in docks] == ["panel"]
    central = window.centralWidget()
    assert central is not None
    assert central.objectName() == "canvas"
    assert app.build().main_window is window


def test_no_toolkit_object_exists_before_the_build() -> None:
    """Constructing a session touches no toolkit object and reads no file."""
    app = QtApp()
    with pytest.raises(RuntimeError, match=r"Call build\(\) before"):
        _ = app.main_window
    try:
        assert app.build().main_window.findChildren(QDockWidget) != []
    finally:
        app.shutdown()


def test_the_configuration_names_the_container() -> None:
    """A session naming Qt comes up on the Qt container without a class."""
    app = AppContainer.from_config({"frontend": "pyqt", "name": "from-file"})
    assert isinstance(app, QtAppContainer)
    assert app.frontend is Qt
    try:
        assert app.build().main_window.windowTitle() == "from-file"
    finally:
        app.shutdown()


def test_every_placement_lands_where_it_asked(
    window: QMainWindow, build: Callable[..., QtAppContainer]
) -> None:
    """One pass over the views fills docks, the centre, a menu and a toolbar."""
    app = build(QtApp)
    # inspected before the shutdown, which destroys the widgets it built
    attach(window, dict(app.views))

    docks = window.findChildren(QDockWidget)
    assert [_widget(d).objectName() for d in docks] == ["panel"]
    central = window.centralWidget()
    assert central is not None
    assert central.objectName() == "canvas"

    menus = _menus(window)
    assert [m.title() for m in menus] == ["File"]
    assert [a.objectName() for a in menus[0].actions()] == ["save"]

    toolbars = window.findChildren(QToolBar)
    assert [t.objectName() for t in toolbars] == ["Plans"]
    assert [a.objectName() for a in toolbars[0].actions()] == ["acquire"]


def test_one_menu_holds_every_entry_asking_for_it(window: QMainWindow) -> None:
    """The menu is created once and found again, not created per entry."""
    # a QAction is not reparented by addAction, so the caller keeps it alive
    views: dict[str, AttachableComponent] = {
        "save": Save("save"),
        "open": Open("open"),
    }
    attach(window, views)

    menus = _menus(window)
    assert len(menus) == 1
    assert [a.objectName() for a in menus[0].actions()] == ["save", "open"]


def test_several_central_views_share_the_area_as_tabs(window: QMainWindow) -> None:
    attach(window, {"canvas": Canvas("canvas"), "other": Other("other")})

    tabs = window.centralWidget()
    assert isinstance(tabs, QTabWidget)
    assert [tabs.tabText(i) for i in range(tabs.count())] == ["canvas", "other"]


def test_a_view_of_the_wrong_toolkit_type_is_refused(window: QMainWindow) -> None:
    """The placement decides what the view must be, and only Qt knows that."""
    with pytest.raises(TypeError, match="needs a QWidget, but NotAWidget is not one"):
        attach(window, {"stray": NotAWidget("stray")})


def test_a_view_of_the_wrong_toolkit_type_is_refused_before_it_is_built() -> None:
    """Qt's requirement table is read with the declarations, not at attach."""

    class Wrong(QtAppContainer):
        __slots__ = ()

        stray: AsView[NotAWidget]

    with pytest.raises(
        TypeError, match=r"Wrong\.stray .* needs a QWidget, but NotAWidget is not one"
    ):
        Wrong().build()


def _menus(window: QMainWindow) -> list[QMenu]:
    return window.findChildren(QMenu)


def _widget(dock: QDockWidget) -> QWidget:
    inner = dock.widget()
    assert inner is not None
    return inner


class Gain:
    """A presenter a command can be filled with."""

    def __init__(self, name: str, /) -> None:
        self.name = name
        self.value = 3.0


class CommandApp(QtAppContainer):
    gain: AsPresenter[Gain]


def test_a_command_is_filled_from_the_session() -> None:
    """The session builds its components out of the application's own store."""
    app = CommandApp().build()
    seen: list[Gain] = []

    def note(gain: Gain) -> None:
        seen.append(gain)

    try:
        app.model.register_action(Action(id="probe.note", title="Note", callback=note))
        app.model.commands.execute_command("probe.note")
        assert seen == [app.gain]
    finally:
        app.shutdown()


def test_the_window_is_built_against_the_session_application(
    qapp: QApplication,
    build: Callable[..., QtAppContainer],
) -> None:
    """A menu bar on the window is filled from the session's own registries."""
    app = build(CommandApp)
    app.model.register_action(
        Action(
            id="probe.note",
            title="Note",
            callback=lambda: None,
            menus=[MenuRule(id="probe/tools")],
        )
    )
    menu_bar = app.main_window.setModelMenuBar({"probe/tools": "Tools"})
    tools = next(m for m in menu_bar.findChildren(QMenu) if m.title() == "Tools")
    assert [a.text() for a in tools.actions()] == ["Note"]


def test_the_session_holds_the_application_it_runs_on() -> None:
    """A session adopting a running application still keeps a reference."""
    app = QtApp()
    with pytest.raises(RuntimeError, match=r"Call build\(\) before"):
        _ = app.app
    app.build()
    try:
        assert app.app is QApplication.instance()
    finally:
        app.shutdown()


BUILDS_ITS_OWN = """
from qtpy.QtWidgets import QApplication, QWidget

from redsun.experimental import AsView, Placement
from redsun.experimental.containers.qt import Central, QtAppContainer


class Panel(QWidget):
    placement: Placement = Central()

    def __init__(self, name, /):
        super().__init__()
        self.name = name


class Standalone(QtAppContainer):
    __slots__ = ()

    panel: AsView[Panel]


assert QApplication.instance() is None
session = Standalone().build()
assert session.app is QApplication.instance()
assert session.main_window.centralWidget() is not None
# what run() does before handing over to the event loop
session.app.aboutToQuit.connect(session.shutdown)
session.shutdown()
"""


def test_a_session_that_makes_its_own_application_keeps_it_alive() -> None:
    """Drive a session the way a program does, with no fixture holding anything.

    Run in a subprocess, because the suite's ``qapp`` fixture holds an
    application for the whole run and Qt allows one per process, so nothing in
    here can reach this path. It covers two things the fixture hides: an
    application the session made is collected between build steps unless the
    session holds it, and Qt aborts when the next widget is constructed; and
    connecting ``aboutToQuit`` to a session's method takes a weak reference to
    the session. The exit code is the assertion, since the first of those
    aborts the process rather than raising.
    """
    result = subprocess.run(
        [sys.executable, "-c", BUILDS_ITS_OWN],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_shutdown_destroys_the_widgets_the_session_built() -> None:
    """A QWidget outlives its last Python reference whenever C++ owns it.

    Holding a view across the shutdown is what shows the difference: dropping
    the component would leave the widget alive, and the wrapper only reports a
    destroyed one once ``deleteLater`` has been carried out.
    """
    app = QtApp().build()
    panel = app.views["panel"]
    window = app.main_window
    assert isinstance(panel, QWidget)

    app.shutdown()

    with pytest.raises(RuntimeError):
        panel.objectName()
    with pytest.raises(RuntimeError):
        window.windowTitle()
    with pytest.raises(RuntimeError, match=r"Call build\(\) before"):
        _ = app.main_window


TEARDOWN_ORDER: list[str] = []


class Closing(QWidget):
    """A view that records its own teardown and its widget's."""

    placement: Placement = Dock("left")

    def __init__(self, name: str, /) -> None:
        super().__init__()
        self.name = name

    def shutdown(self) -> None:
        TEARDOWN_ORDER.append("shutdown")

    def closeEvent(self, event: QCloseEvent | None) -> None:
        TEARDOWN_ORDER.append("closed")
        if event is not None:
            super().closeEvent(event)


class ClosingApp(QtAppContainer):
    __slots__ = ()

    panel: AsView[Closing]


def test_a_view_is_shut_down_before_its_widget_is_destroyed() -> None:
    """A component's own teardown may touch the widget it was built around."""
    TEARDOWN_ORDER.clear()
    ClosingApp().build().shutdown()
    assert TEARDOWN_ORDER == ["shutdown", "closed"]


class SaveApp(QtAppContainer):
    __slots__ = ()

    config: ClassVar[dict[str, Any]] = {"name": "save-session"}


def _answer(monkeypatch: pytest.MonkeyPatch, path: str) -> None:
    """Make the save dialog return *path* without showing anything."""
    monkeypatch.setattr(
        "redsun.experimental.containers.qt._container.QFileDialog.getSaveFileName",
        staticmethod(lambda *a, **k: (path, "")),
    )


def test_the_save_action_writes_where_the_dialog_points(
    qapp: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    build: Callable[..., QtAppContainer],
) -> None:
    target = tmp_path / "written.yaml"
    _answer(monkeypatch, str(target))
    session = build(SaveApp)

    session.model.commands.execute_command("save-session.save_configuration")

    assert yaml.safe_load(target.read_text())["name"] == "save-session"


def test_a_cancelled_dialog_writes_nothing(
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    build: Callable[..., QtAppContainer],
) -> None:
    _answer(monkeypatch, "")
    asked: list[object] = []
    monkeypatch.setattr(SaveApp, "write", lambda self, path: asked.append(path))
    session = build(SaveApp)

    session.model.commands.execute_command("save-session.save_configuration")

    assert asked == []


def test_choosing_a_source_is_reported_rather_than_written(
    qapp: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    build: Callable[..., QtAppContainer],
) -> None:
    """Only the session knows which files it read, so Qt cannot refuse this."""
    source = tmp_path / "shared.yaml"
    source.write_text(yaml.safe_dump({"name": "save-session"}))
    _answer(monkeypatch, str(source))
    warned: list[str] = []
    monkeypatch.setattr(
        "redsun.experimental.containers.qt._container.QMessageBox.warning",
        staticmethod(lambda _parent, _title, text, *a, **k: warned.append(text)),
    )
    session = build(SaveApp, str(source))

    session.model.commands.execute_command("save-session.save_configuration")

    assert yaml.safe_load(source.read_text()) == {"name": "save-session"}
    assert "shared.yaml is a source this session was built from" in warned[0]


def test_the_action_joins_the_menu_a_window_can_show(
    qapp: QApplication, build: Callable[..., QtAppContainer]
) -> None:
    session = build(SaveApp)

    menu_bar = session.main_window.setModelMenuBar({SAVE_MENU: "File"})

    entries = next(m for m in menu_bar.findChildren(QMenu) if m.title() == "File")
    assert [entry.text() for entry in entries.actions()] == ["Save configuration as..."]
