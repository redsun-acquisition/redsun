"""Tests for attaching views to a Qt main window."""

from __future__ import annotations

import re
import subprocess
import sys
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, cast

import pytest
import yaml
from app_model import Action, Application
from app_model.types import MenuRule
from psygnal import Signal, emit_queued
from qtpy.QtCore import QEvent
from qtpy.QtGui import QAction, QCloseEvent
from qtpy.QtWidgets import (
    QApplication,
    QDockWidget,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QToolBar,
    QWidget,
)

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

    from redsun.testing import BuildSession

from mock_bundle.panels import Panel

from redsun import (
    AsHook,
    AsPresenter,
    AsView,
    AttachableComponent,
    Placement,
    Session,
    slot,
)
from redsun.qt import (
    ASK_ON_CLOSE,
    SAVE_MENU,
    Central,
    Dock,
    MenuItem,
    Qt,
    QtHook,
    QtSession,
    ToolBarItem,
    attach,
)

pytestmark = pytest.mark.qt


class Mover:
    """A presenter reporting where a motor went."""

    sig_moved = Signal(str, float)

    def __init__(self, name: str) -> None:
        self.name = name


class Readout(QWidget):
    """A view writing each reading into a child widget, as a real view does."""

    placement: Placement = Dock("left")

    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.name = name
        self.label = QLabel(self)
        self.texts: list[str] = []

    @slot
    def note(self, motor: str, position: float) -> None:
        self.label.setText(f"{motor} {position}")
        self.texts.append(self.label.text())


class Wired(QtSession):
    config: ClassVar[dict[str, Any]] = {"wiring": {"mover.sig_moved": "readout.note"}}

    mover: AsPresenter[Mover]
    readout: AsView[Readout]


class Canvas(QWidget):
    placement: Placement = Central()

    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.name = name


class Other(QWidget):
    placement: Placement = Central()

    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.name = name


class Save(QAction):
    placement: Placement = MenuItem("File")

    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__(name, parent)
        self.name = name


class Open(QAction):
    placement: Placement = MenuItem("File")

    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__(name, parent)
        self.name = name


class Acquire(QAction):
    placement: Placement = ToolBarItem("Plans")

    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__(name, parent)
        self.name = name


class NotAWidget:
    placement: Placement = Dock("left")

    def __init__(self, name: str) -> None:
        self.name = name


class QtApp(QtSession):
    panel: AsView[Panel]
    canvas: AsView[Canvas]
    save: AsView[Save]
    acquire: AsView[Acquire]


class BrokenPanel(QWidget):
    """A docked view whose constructor raises."""

    placement: Placement = Dock("left")

    def __init__(self, name: str, parent: QWidget) -> None:
        raise RuntimeError("no detector attached")


class BrokenPresenter:
    """A presenter whose constructor raises."""

    def __init__(self, name: str) -> None:
        raise RuntimeError("no calibration file")


class BrokenApp(QtSession):
    panel: AsView[Panel]
    broken_panel: AsView[BrokenPanel]
    broken_ctrl: AsPresenter[BrokenPresenter]


@pytest.fixture
def window(qapp: QApplication) -> Generator[QMainWindow, None, None]:
    """Return an empty main window, deleted after the test."""
    window = QMainWindow()
    yield window
    window.deleteLater()


def _menus(window: QMainWindow) -> list[QMenu]:
    return window.findChildren(QMenu)


def _widget(dock: QDockWidget) -> QWidget:
    inner = dock.widget()
    assert inner is not None
    return inner


class Gain:
    """A presenter a command can be filled with."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.value = 3.0


class CommandApp(QtSession):
    gain: AsPresenter[Gain]


SLOT_RAISES = """
import sys
from collections.abc import Iterator

from psygnal import Signal
from qtpy.QtCore import QTimer
from qtpy.QtWidgets import QApplication, QWidget

import redsun._settings
import redsun.log
from redsun import AsPresenter, AsView, Link, Placement, slot
from redsun.qt import Dock, QtSession

redsun._settings.user_config_dir = lambda *a, **k: sys.argv[1]
redsun.log.user_data_dir = lambda *a, **k: sys.argv[1]


class Ticker:
    sig_tick = Signal()

    def __init__(self, name: str) -> None:
        self.name = name


class Panel(QWidget):
    placement: Placement = Dock("left")

    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.name = name

    @slot
    def on_tick(self) -> None:
        raise RuntimeError("the panel failed")


class Raising(QtSession):
    ticker: AsPresenter[Ticker]
    panel: AsView[Panel]

    def wire(self) -> Iterator[Link]:
        yield self.ticker.sig_tick, self.panel.on_tick


qt = QApplication([])
session = Raising()
QTimer.singleShot(200, lambda: session.ticker.sig_tick.emit())
QTimer.singleShot(600, lambda: print("still running", flush=True))
QTimer.singleShot(800, qt.quit)
session.run()
"""


BUILDS_ITS_OWN = """
from qtpy.QtWidgets import QApplication, QWidget

from redsun import AsView, Placement
from redsun.qt import Central, QtSession


class Panel(QWidget):
    placement: Placement = Central()

    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.name = name


class Standalone(QtSession):
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


class Closing(QWidget):
    """A view that records its own teardown and its widget's."""

    placement: Placement = Dock("left")

    def __init__(self, name: str, parent: QWidget, record: list[str]) -> None:
        super().__init__(parent)
        self.name = name
        self.record = record

    def shutdown(self) -> None:
        self.record.append("shutdown")

    def closeEvent(self, event: QCloseEvent | None) -> None:
        self.record.append("closed")
        if event is not None:
            super().closeEvent(event)


class ClosingApp(QtSession):
    panel: AsView[Closing]


class SaveApp(QtSession):
    config: ClassVar[dict[str, Any]] = {"session": "save-session"}


class Receiving(QWidget):
    """A view keeping the parent the session passed it."""

    placement: Placement = Dock("left")

    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.name = name
        self.given = parent


class Unparented(QWidget):
    placement: Placement = Dock("left")

    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name


class OptionallyParented(QWidget):
    placement: Placement = Dock("left")

    def __init__(self, name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.name = name


class KeywordParent(QWidget):
    placement: Placement = Dock("left")

    def __init__(self, name: str, *, parent: QWidget) -> None:
        super().__init__(parent)
        self.name = name


class ObjectNamed(QWidget):
    placement: Placement = Dock("left")

    def __init__(self, name: object, parent: QWidget) -> None:
        super().__init__(parent)
        self.name = str(name)


class HelperKeeping(QWidget):
    """A view parenting a helper widget to the window it was given."""

    placement: Placement = Dock("left")

    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.name = name
        self.helper = QWidget(parent)


class Breaking(QWidget):
    """A view failing after it has joined the window."""

    placement: Placement = Dock("right")

    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__(parent)
        raise RuntimeError(f"{name} fails after joining the window")


STARTS_WITH = re.escape("does not start with '(name: str, parent: QWidget)'")


class ReceivingApp(QtSession):
    panel: AsView[Receiving]


class UnparentedApp(QtSession):
    panel: AsView[Unparented]


class OptionallyParentedApp(QtSession):
    panel: AsView[OptionallyParented]


class KeywordParentApp(QtSession):
    panel: AsView[KeywordParent]


class ObjectNamedApp(QtSession):
    panel: AsView[ObjectNamed]


class GivenParentApp(QtSession):
    config: ClassVar[dict[str, Any]] = {"views": {"panel": {"parent": None}}}

    panel: AsView[Receiving]


@dataclass(frozen=True)
class Nowhere(Placement):
    """A placement Qt does not attach."""


class Misplaced(QWidget):
    """A view whose placement only the built instance answers, wrongly."""

    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.name = name

    @property
    def placement(self) -> Placement:
        return Nowhere()


class MisplacedApp(QtSession):
    panel: AsView[Misplaced]


class BreakingApp(QtSession):
    helper: AsView[HelperKeeping]
    broken: AsView[Breaking]


def _answer(monkeypatch: pytest.MonkeyPatch, path: str) -> None:
    """Make the save dialog return *path* without showing anything."""
    monkeypatch.setattr(
        "redsun.qt._session.QFileDialog.getSaveFileName",
        staticmethod(lambda *a, **k: (path, "")),
    )


class Tunable:
    """Presenter whose one setting is what a session has to offer to save."""

    def __init__(self, name: str, *, step: float = 1.0) -> None:
        self.name = name
        self.step = step

    def serialize(self) -> dict[str, float]:
        return {"step": self.step}


class PromptApp(QtSession):
    config: ClassVar[dict[str, Any]] = {"session": "closing-session"}

    tunable: AsPresenter[Tunable]


class AlwaysCloses:
    """Hook answering the close itself, in place of the prompt."""

    def __init__(self) -> None:
        self.asked = 0

    def confirm_close(self) -> bool:
        self.asked += 1
        return True


class HookedApp(PromptApp):
    confirm_close: AsHook[AlwaysCloses]


def _press(
    monkeypatch: pytest.MonkeyPatch,
    button: QMessageBox.StandardButton,
    *,
    dont_ask: bool = False,
) -> list[QMessageBox]:
    """Answer the next close prompt with *button*, without showing it."""
    shown: list[QMessageBox] = []

    def exec_(prompt: QMessageBox) -> int:
        shown.append(prompt)
        if dont_ask:
            box = prompt.checkBox()
            assert box is not None
            box.setChecked(True)
        return int(button)

    monkeypatch.setattr(QMessageBox, "exec", exec_)
    return shown


def test_the_session_owns_an_application_named_after_it(
    qapp: QApplication, build: BuildSession
) -> None:
    """Create an application model named after the session and drop it on shutdown."""
    app = QtApp()
    with pytest.raises(RuntimeError, match=r"Call build\(\) before"):
        _ = app.model
    build(app)
    assert app.model is Application.get_app("QtApp")
    app.shutdown()
    assert Application.get_app("QtApp") is None


def test_two_sessions_of_one_name_refuse_to_coexist(
    qapp: QApplication,
    build: BuildSession,
) -> None:
    """Refuse to build a second session under a name already in use."""
    build(QtApp)
    with pytest.raises(ValueError, match="already exists"):
        QtApp().build()


def test_the_name_is_free_again_after_shutdown(
    qapp: QApplication, build: BuildSession
) -> None:
    """Free the session name on shutdown so the same session can be built again."""
    for _ in range(3):
        app = build(QtApp)
        assert app.model.name == "QtApp"
        app.shutdown()


def test_the_container_builds_its_own_window(
    qapp: QApplication,
    build: BuildSession,
) -> None:
    """Build a main window titled after the session, with docks and a central widget."""
    app = build(QtApp)
    window = app.main_window
    assert window.windowTitle() == "QtApp"
    docks = window.findChildren(QDockWidget)
    assert [_widget(d).objectName() for d in docks] == ["panel"]
    central = window.centralWidget()
    assert central is not None
    assert central.objectName() == "canvas"


def test_building_again_keeps_the_window(
    qapp: QApplication, build: BuildSession
) -> None:
    """Keep the same main window when a built session is built again."""
    app = build(QtApp)

    assert app.build().main_window is app.main_window


def test_no_toolkit_object_exists_before_the_build(
    qapp: QApplication, build: BuildSession
) -> None:
    """Create no main window until the session is built."""
    app = QtApp()
    with pytest.raises(RuntimeError, match=r"Call build\(\) before"):
        _ = app.main_window
    assert build(app).main_window.findChildren(QDockWidget) != []


def test_the_configuration_names_the_container(
    qapp: QApplication, build: BuildSession
) -> None:
    """Return a QtSession from a configuration whose frontend is qt."""
    app = Session.from_config({"frontend": "qt", "session": "from-file"})
    assert isinstance(app, QtSession)
    assert app.frontend is Qt
    assert build(app).main_window.windowTitle() == "from-file"


def test_every_placement_lands_where_it_asked(
    window: QMainWindow, build: BuildSession
) -> None:
    """Attach each view to its dock, the central area, a menu or a toolbar."""
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
    """Put every action asking for one menu into a single menu."""
    # a QAction is not reparented by addAction, so the caller keeps it alive
    views: dict[str, AttachableComponent] = {
        "save": Save("save", parent=window),
        "open": Open("open", parent=window),
    }
    attach(window, views)

    menus = _menus(window)
    assert len(menus) == 1
    assert [a.objectName() for a in menus[0].actions()] == ["save", "open"]


def test_several_central_views_share_the_area_as_tabs(window: QMainWindow) -> None:
    """Put several central views into tabs of one tab widget."""
    attach(
        window,
        {
            "canvas": Canvas("canvas", parent=window),
            "other": Other("other", parent=window),
        },
    )

    tabs = window.centralWidget()
    assert isinstance(tabs, QTabWidget)
    assert [tabs.tabText(i) for i in range(tabs.count())] == ["canvas", "other"]


def test_a_view_of_the_wrong_toolkit_type_is_refused(window: QMainWindow) -> None:
    """Refuse to attach a view that is not the QWidget its placement needs."""
    with pytest.raises(TypeError, match="needs a QWidget, but NotAWidget is not one"):
        attach(window, {"stray": NotAWidget("stray")})


def test_a_view_of_the_wrong_toolkit_type_is_skipped_before_it_is_built(
    qapp: QApplication, build: BuildSession, caplog: pytest.LogCaptureFixture
) -> None:
    """Skip at declaration a view that is not the Qt type its placement needs."""

    class Wrong(QtSession):
        stray: AsView[NotAWidget]

    app = build(Wrong)

    assert "stray" not in app.views
    assert re.search(
        r"Wrong\.stray .* needs a QWidget, but NotAWidget is not one", caplog.text
    )


def test_a_command_is_filled_from_the_session(
    qapp: QApplication, build: BuildSession
) -> None:
    """Inject a value the session provides into a registered command's callback."""
    app = build(CommandApp)
    seen: list[Gain] = []

    def note(gain: Gain) -> None:
        seen.append(gain)

    app.model.register_action(Action(id="probe.note", title="Note", callback=note))
    app.model.commands.execute_command("probe.note")
    assert seen == [app.gain]


def test_the_window_is_built_against_the_session_application(
    qapp: QApplication,
    build: BuildSession,
) -> None:
    """Fill the window's menu bar from the session application's menus."""
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


def test_the_session_holds_the_application_it_runs_on(
    qapp: QApplication, build: BuildSession
) -> None:
    """Hold the running QApplication after the build, and refuse access before it."""
    app = QtApp()
    with pytest.raises(RuntimeError, match=r"Call build\(\) before"):
        _ = app.app
    build(app)
    assert app.app is QApplication.instance()


def test_a_session_that_makes_its_own_application_keeps_it_alive() -> None:
    """Keep alive a QApplication the session created, run in a separate process."""
    # Run in a subprocess: the suite's `qapp` fixture holds an application for the
    # whole run and Qt allows one per process, so this path cannot be reached here.
    result = subprocess.run(
        [sys.executable, "-c", BUILDS_ITS_OWN],
        capture_output=True,
        text=True,
        check=False,
    )
    # The exit code is the assertion: an application the session made and does not
    # hold is collected between build steps, and Qt then aborts the process at the
    # next widget rather than raising.
    assert result.returncode == 0, result.stdout + result.stderr


def test_an_exception_in_a_slot_is_logged_and_the_window_carries_on(
    tmp_path: Path,
) -> None:
    """Log an exception a view slot raised while the window runs, and keep running."""
    # Run in a subprocess: the exception has to reach the Qt event loop, which only
    # `run` starts.
    result = subprocess.run(
        [sys.executable, "-c", SLOT_RAISES, str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "the panel failed" in output
    assert "still running" in output


def test_shutdown_destroys_the_widgets_the_session_built(
    qapp: QApplication, build: BuildSession
) -> None:
    """Destroy the main window and every view widget on shutdown."""
    app = build(QtApp)
    # The view is held across the shutdown because a QWidget outlives its last Python
    # reference whenever C++ owns it: dropping the component would leave the widget
    # alive, and the wrapper reports it destroyed only once `deleteLater` has run.
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


def test_a_view_is_given_the_main_window_as_its_parent(
    qapp: QApplication, build: BuildSession
) -> None:
    """Pass the main window as the parent of a view."""
    app = build(ReceivingApp)

    assert app.panel.given is app.main_window


@pytest.mark.parametrize(
    ("app", "match"),
    [
        (UnparentedApp, STARTS_WITH),
        (OptionallyParentedApp, STARTS_WITH),
        (KeywordParentApp, STARTS_WITH),
        (ObjectNamedApp, STARTS_WITH),
    ],
    ids=[
        "no-parent",
        "optional-parent",
        "keyword-only-parent",
        "name-not-str",
    ],
)
def test_a_view_not_shaped_for_qt_is_skipped(
    app: type[QtSession],
    match: str,
    qapp: QApplication,
    build: BuildSession,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Skip a view whose constructor does not start with `(name: str, parent)`."""
    built = build(app)

    assert "panel" not in built.views
    assert re.search(match, caplog.text)


def test_a_view_given_a_parent_by_its_configuration_is_skipped(
    qapp: QApplication, build: BuildSession, caplog: pytest.LogCaptureFixture
) -> None:
    """Skip a view whose configuration also passes a parent."""
    app = build(GivenParentApp)

    assert "panel" not in app.views
    assert "multiple values for keyword argument 'parent'" in caplog.text


def test_a_view_refused_once_built_is_removed_from_the_window(
    qapp: QApplication, build: BuildSession, caplog: pytest.LogCaptureFixture
) -> None:
    """Remove a view from the window when its built instance has a bad placement."""
    app = build(MisplacedApp)
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    assert "panel" not in app.views
    assert app.main_window.findChildren(Misplaced) == []
    assert "asks to be attached as 'Nowhere'" in caplog.text


def test_a_view_failing_after_joining_the_window_leaves_nothing_in_it(
    qapp: QApplication, build: BuildSession
) -> None:
    """Remove a failed view from the window and keep what other views parented to it."""
    app = build(BreakingApp)
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    assert app.main_window.findChildren(Breaking) == []
    assert app.helper.helper.parent() is app.main_window


def test_a_view_is_shut_down_before_its_widget_is_destroyed(
    qapp: QApplication, build: BuildSession
) -> None:
    """Call a view's shutdown before its widget is closed."""
    record: list[str] = []
    build(ClosingApp, {"views": {"panel": {"record": record}}}).shutdown()
    assert record == ["shutdown", "closed"]


def test_the_save_action_writes_where_the_dialog_points(
    qapp: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    build: BuildSession,
) -> None:
    """Write the configuration to the path the save dialog returns."""
    target = tmp_path / "written.yaml"
    _answer(monkeypatch, str(target))
    session = build(SaveApp)

    session.model.commands.execute_command("save-session.save_configuration")

    assert yaml.safe_load(target.read_text())["session"] == "save-session"


def test_a_cancelled_dialog_writes_nothing(
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    build: BuildSession,
) -> None:
    """Write nothing when the save dialog is cancelled."""
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
    build: BuildSession,
) -> None:
    """Warn and leave the file unchanged when saving over a configuration source."""
    source = tmp_path / "shared.yaml"
    source.write_text(yaml.safe_dump({"session": "save-session"}))
    _answer(monkeypatch, str(source))
    warned: list[str] = []
    monkeypatch.setattr(
        "redsun.qt._session.QMessageBox.warning",
        staticmethod(lambda _parent, _title, text, *a, **k: warned.append(text)),
    )
    session = build(SaveApp, str(source))

    session.model.commands.execute_command("save-session.save_configuration")

    assert yaml.safe_load(source.read_text()) == {"session": "save-session"}
    assert "shared.yaml is a source this session was built from" in warned[0]


def test_the_action_joins_the_menu_a_window_can_show(
    qapp: QApplication, build: BuildSession
) -> None:
    """Add the save action to the File menu of the window's menu bar."""
    session = build(SaveApp)

    menu_bar = session.main_window.setModelMenuBar({SAVE_MENU: "File"})

    entries = next(m for m in menu_bar.findChildren(QMenu) if m.title() == "File")
    assert [entry.text() for entry in entries.actions()] == ["Save configuration as..."]


def test_a_session_nobody_has_changed_closes_without_asking(
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    build: BuildSession,
) -> None:
    """Close an unchanged session without showing the close prompt."""
    shown = _press(monkeypatch, QMessageBox.StandardButton.Cancel)

    assert build(PromptApp).main_window.close()
    assert shown == []


def test_cancelling_the_prompt_keeps_the_session_open(
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    build: BuildSession,
) -> None:
    """Keep a changed session open, and its window visible, when the prompt is cancelled."""
    session = build(PromptApp)
    session.tunable.step = 5.0
    session.main_window.show()
    _press(monkeypatch, QMessageBox.StandardButton.Cancel)

    assert not session.main_window.close()
    assert session.main_window.isVisible()


def test_discarding_closes_without_writing(
    qapp: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    build: BuildSession,
) -> None:
    """Close without writing a file when the prompt answers Discard."""
    target = tmp_path / "discarded.yaml"
    _answer(monkeypatch, str(target))
    session = build(PromptApp)
    session.tunable.step = 5.0
    _press(monkeypatch, QMessageBox.StandardButton.Discard)

    assert session.main_window.close()
    assert not target.exists()


def test_saving_writes_and_then_closes(
    qapp: QApplication,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    build: BuildSession,
) -> None:
    """Write the changed configuration and close when the prompt answers Save."""
    target = tmp_path / "on-close.yaml"
    _answer(monkeypatch, str(target))
    _press(monkeypatch, QMessageBox.StandardButton.Save)
    session = build(PromptApp)
    session.tunable.step = 5.0

    assert session.main_window.close()
    assert yaml.safe_load(target.read_text())["presenters"]["tunable"]["step"] == 5.0


def test_a_cancelled_save_dialog_keeps_the_session_open(
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    build: BuildSession,
) -> None:
    """Keep the session open when the save dialog after the prompt is cancelled."""
    _answer(monkeypatch, "")
    _press(monkeypatch, QMessageBox.StandardButton.Save)
    session = build(PromptApp)
    session.tunable.step = 5.0

    assert not session.main_window.close()


def test_dont_ask_again_is_remembered_between_runs(
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    build: BuildSession,
) -> None:
    """Store the 'do not ask again' choice and skip the prompt in the next session."""
    first = build(PromptApp)
    first.tunable.step = 5.0
    _press(monkeypatch, QMessageBox.StandardButton.Discard, dont_ask=True)
    assert first.main_window.close()
    assert first.settings.get(ASK_ON_CLOSE) is False
    first.shutdown()

    second = build(PromptApp)
    second.tunable.step = 9.0
    shown = _press(monkeypatch, QMessageBox.StandardButton.Cancel)

    assert second.main_window.close()
    assert shown == []


def test_a_hook_answers_the_close_in_place_of_the_prompt(
    qapp: QApplication,
    monkeypatch: pytest.MonkeyPatch,
    build: BuildSession,
) -> None:
    """Ask the close hook instead of showing the close prompt."""
    session = build(HookedApp)
    session.tunable.step = 5.0
    shown = _press(monkeypatch, QMessageBox.StandardButton.Cancel)

    assert session.main_window.close()
    hook = cast("AlwaysCloses", session.hooks[QtHook.CONFIRM_CLOSE])
    assert hook.asked == 1
    assert shown == []


def test_a_dock_on_an_unknown_edge_is_refused() -> None:
    """Refuse a dock on an edge Qt has no area for, naming the edges it has."""
    with pytest.raises(ValueError, match="'bottm'.*left, right, top, bottom"):
        Dock("bottm")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("value", "placement"),
    [
        ("left", Dock("left")),
        ("bottom", Dock("bottom")),
        ("central", Central()),
        ({"dock": "top"}, Dock("top")),
        ({"dock": "right", "group": "tools"}, Dock("right", group="tools")),
        ({"menu": "Acquire"}, MenuItem("Acquire")),
        ({"toolbar": "Acquisition"}, ToolBarItem("Acquisition")),
    ],
)
def test_qt_reads_each_placement_a_session_file_writes(
    value: object, placement: Placement
) -> None:
    """Read each word and mapping a session file uses for a Qt placement."""
    assert Qt.read_placement(value) == placement


@pytest.mark.parametrize(
    "value",
    [
        "middle",
        {"dock": "middle"},
        {"dok": "left"},
        {"menu": "A", "toolbar": "B"},
        {"dock": "left", "group": "g", "extra": "x"},
        3,
    ],
)
def test_qt_refuses_a_placement_it_cannot_read(value: object) -> None:
    """Refuse a value naming no Qt placement, listing the forms Qt reads."""
    with pytest.raises(ValueError, match="left, right, top, bottom, central"):
        Qt.read_placement(value)


def test_a_failed_view_leaves_its_reason_where_it_would_have_been(
    qapp: QApplication, build: BuildSession
) -> None:
    """Put a widget naming a failed view and its reason in the dock it asked for."""
    session = build(BrokenApp)
    docks = {d.objectName(): d for d in session.main_window.findChildren(QDockWidget)}
    labels = [
        label.text() for label in _widget(docks["broken_panel"]).findChildren(QLabel)
    ]
    assert labels == ["broken_panel could not be built:\nno detector attached"]


def test_the_status_bar_counts_the_components_that_failed(
    qapp: QApplication, build: BuildSession
) -> None:
    """Show in the status bar how many components failed to build."""
    session = build(BrokenApp)
    bar = session.main_window.statusBar()
    assert bar is not None
    assert [b.text() for b in bar.findChildren(QPushButton)] == ["2 components failed"]


def test_a_view_slot_runs_on_the_main_thread(
    qapp: QApplication, build: BuildSession
) -> None:
    """Connect a view slot to run on the main thread."""
    session = build(Wired)

    assert [link.thread for link in session.connections] == ["main"]


def test_a_queued_emission_is_delivered_before_the_widgets_are_destroyed(
    qapp: QApplication, build: BuildSession
) -> None:
    """Deliver a signal queued from a worker thread once, during shutdown."""
    session = build(Wired)
    readout = session.readout

    # emitted from a worker, the reading waits in the queue for the main
    # thread, and nothing runs the event loop before the shutdown
    worker = threading.Thread(target=lambda: session.mover.sig_moved.emit("x", 1.0))
    worker.start()
    worker.join()
    session.shutdown()

    assert readout.texts == ["x 1.0"]
    emit_queued()
    assert readout.texts == ["x 1.0"]


def test_a_qt_session_writes_its_start_profile(
    qapp: QApplication, tmp_path: Path, build: BuildSession
) -> None:
    """Write a start profile for a Qt session, as `MyApp(profile="start")` asks."""
    build(QtApp(profile="start", profile_dir=tmp_path)).shutdown()

    assert len(list(tmp_path.glob("*.html"))) == 1
