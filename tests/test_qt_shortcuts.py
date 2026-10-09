"""Tests for the keyboard shortcuts a Qt session binds and lists."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, ClassVar

import pytest
from app_model.backends.qt import QModelMenu
from mock_bundle.menu_callbacks import Executed
from qtpy.QtCore import Qt as QtNamespace
from qtpy.QtGui import QAction, QKeySequence
from qtpy.QtWidgets import (
    QApplication,
    QComboBox,
    QLineEdit,
    QTableWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from redsun import (
    AsPresenter,
    AsView,
    ConfigurationError,
    Placement,
    provides,
    shortcut,
)
from redsun.qt import WINDOW_MENU, Central, Dock, MenuItem, QtSession
from redsun.view.qt._shortcuts_dialog import ShortcutsDialog
from tests.sdk.view.helpers import key_click

if TYPE_CHECKING:
    from redsun.testing import BuildSession

pytestmark = pytest.mark.qt

CTRL = QtNamespace.KeyboardModifier.ControlModifier


class Panel(QWidget):
    """A view with a window key, a key of its own, and a field to focus."""

    placement: Placement = Dock("left")

    def __init__(
        self, name: str, parent: QWidget, ran: list[str] | None = None
    ) -> None:
        super().__init__(parent)
        self.name = name
        self.ran = ran if ran is not None else []
        self.edit = QLineEdit(self)
        QVBoxLayout(self).addWidget(self.edit)

    @shortcut("Ctrl+R", title="Run")
    def run(self) -> None:
        self.ran.append("run")

    @shortcut("F5", title="Refresh", scope="view")
    def refresh(self) -> None:
        self.ran.append("refresh")


class Other(QWidget):
    """A view with only a field to focus."""

    placement: Placement = Dock("right")

    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.name = name
        self.edit = QLineEdit(self)
        QVBoxLayout(self).addWidget(self.edit)


class Tree(QWidget):
    """A view whose Left key acts only while it is ready, beside a tree using Left."""

    placement: Placement = Dock("left")

    def __init__(
        self,
        name: str,
        parent: QWidget,
        ran: list[str] | None = None,
        ready: bool = False,
        broken: bool = False,
    ) -> None:
        super().__init__(parent)
        self.name = name
        self.ran = ran if ran is not None else []
        self.ready = ready
        self.broken = broken
        self.tree = QTreeWidget(self)
        self.top = QTreeWidgetItem(["top"])
        QTreeWidgetItem(self.top, ["leaf"])
        self.tree.addTopLevelItem(self.top)
        self.top.setExpanded(True)
        self.tree.setCurrentItem(self.top)
        self.edit = QLineEdit(self)
        layout = QVBoxLayout(self)
        layout.addWidget(self.tree)
        layout.addWidget(self.edit)

    def _is_ready(self) -> bool:
        if self.broken:
            raise RuntimeError("cannot tell")
        return self.ready

    @shortcut("Left", title="Back", scope="view", when=_is_ready)
    def back(self) -> None:
        self.ran.append("back")


class Walker(QWidget):
    """A view with a window key on Left."""

    placement: Placement = Dock("right")

    def __init__(
        self, name: str, parent: QWidget, ran: list[str] | None = None
    ) -> None:
        super().__init__(parent)
        self.name = name
        self.ran = ran if ran is not None else []

    @shortcut("Left", title="Walk")
    def walk(self) -> None:
        self.ran.append("walk")


class Misspelt(Panel):
    """A view whose key Qt cannot read."""

    @shortcut("Ctrl+Period", title="Pause")
    def pause(self) -> None: ...


class KeysApp(QtSession):
    config: ClassVar[dict[str, Any]] = {"session": "keys-session"}

    panel: AsView[Panel]
    other: AsView[Other]


class MisspeltApp(QtSession):
    config: ClassVar[dict[str, Any]] = {"session": "misspelt-session"}

    panel: AsView[Misspelt]


class Shadow(QWidget):
    """A central view whose own key is the window's run key."""

    placement: Placement = Central()

    def __init__(
        self, name: str, parent: QWidget, ran: list[str] | None = None
    ) -> None:
        super().__init__(parent)
        self.name = name
        self.ran = ran if ran is not None else []
        self.edit = QLineEdit(self)
        QVBoxLayout(self).addWidget(self.edit)

    @shortcut("Ctrl+R", title="Run here", scope="view")
    def run_here(self) -> None:
        self.ran.append("here")


class MenuThing(QAction):
    """A view shown as a menu entry, asking for a key of its own view."""

    placement: Placement = MenuItem("Tools")

    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__(name, parent)
        self.name = name

    @shortcut("F7", title="Thing", scope="view")
    def thing(self) -> None: ...


class MenuThingApp(QtSession):
    config: ClassVar[dict[str, Any]] = {"session": "menu-thing-session"}

    panel: AsView[Panel]
    thing: AsView[MenuThing]


class ShadowApp(QtSession):
    config: ClassVar[dict[str, Any]] = {"session": "shadow-session"}

    panel: AsView[Panel]
    shadow: AsView[Shadow]


class TreeApp(QtSession):
    config: ClassVar[dict[str, Any]] = {"session": "tree-session"}

    tree: AsView[Tree]
    other: AsView[Other]


class TreeWalkerApp(QtSession):
    config: ClassVar[dict[str, Any]] = {"session": "tree-walker-session"}

    tree: AsView[Tree]
    walker: AsView[Walker]


class Recorder:
    """Presenter providing the list the commands record into."""

    def __init__(self, name: str, record: list[str]) -> None:
        self.name = name
        self.record = record

    @provides
    def executed(self) -> Executed:
        return Executed(self.record)


class RecordingApp(QtSession):
    config: ClassVar[dict[str, Any]] = {"session": "recording-session"}

    panel: AsView[Panel]
    other: AsView[Other]
    recorder: AsPresenter[Recorder]


@pytest.fixture
def executed() -> list[str]:
    """Return what the session file's commands ran, in order."""
    return []


class CentralOnlyApp(QtSession):
    config: ClassVar[dict[str, Any]] = {"session": "central-only-session"}

    shadow: AsView[Shadow]


def native(key: str) -> str:
    """Return *key* as the dialog shows it."""
    return QKeySequence(key).toString(QKeySequence.SequenceFormat.NativeText)


def opened(app: QtSession) -> ShortcutsDialog:
    """Open the session's shortcut list from its command, and return it."""
    app.model.commands.execute_command(f"{app.name}.show_shortcuts").result()
    dialog = app.main_window.findChild(ShortcutsDialog)
    assert isinstance(dialog, ShortcutsDialog)
    return dialog


def rows(dialog: ShortcutsDialog, group: str) -> list[list[str]]:
    """Return the table's cells as text once *group* is chosen."""
    combo = dialog.findChild(QComboBox)
    table = dialog.findChild(QTableWidget)
    assert combo is not None
    assert table is not None
    combo.setCurrentText(group)
    return [
        [
            item.text() if (item := table.item(row, column)) is not None else ""
            for column in range(table.columnCount())
        ]
        for row in range(table.rowCount())
    ]


def test_a_window_key_runs_its_method_from_anywhere(
    qapp: QApplication, build: BuildSession
) -> None:
    """Run a window key's method with focus in another view."""
    ran: list[str] = []
    app = build(KeysApp, {"views": {"panel": {"ran": ran}}})
    other = app.views["other"]
    assert isinstance(other, Other)

    key_click(other.edit, QtNamespace.Key.Key_R, CTRL)

    assert ran == ["run"]


def test_a_view_key_runs_only_with_focus_in_its_view(
    qapp: QApplication, build: BuildSession
) -> None:
    """Run a view key's method with focus in its view, and not with focus elsewhere."""
    ran: list[str] = []
    app = build(KeysApp, {"views": {"panel": {"ran": ran}}})
    panel, other = app.views["panel"], app.views["other"]
    assert isinstance(panel, Panel)
    assert isinstance(other, Other)

    key_click(other.edit, QtNamespace.Key.Key_F5)
    key_click(panel.edit, QtNamespace.Key.Key_F5)

    assert ran == ["refresh"]


def test_a_conflicting_action_key_is_not_bound(
    qapp: QApplication, build: BuildSession
) -> None:
    """Leave a session file action without the key a component took first."""
    ran: list[str] = []
    action = {
        "id": "keys.note",
        "title": "Note",
        "callback": "mock_bundle.menu_callbacks:note",
        "keybindings": [{"primary": "Ctrl+R"}],
    }
    app = build(KeysApp, {"views": {"panel": {"ran": ran}}, "actions": [action]})
    other = app.views["other"]
    assert isinstance(other, Other)

    key_click(other.edit, QtNamespace.Key.Key_R, CTRL)

    note_keys = [
        a.shortcut().toString()
        for a in app.main_window.findChildren(QAction)
        if a.objectName() == "keys.note"
    ]
    assert ran == ["run"]
    assert all(key == "" for key in note_keys)


def test_a_bad_key_a_component_declares_is_logged_and_left_out(
    qapp: QApplication, build: BuildSession, caplog: pytest.LogCaptureFixture
) -> None:
    """Leave out a component's key Qt cannot read, naming the command and the key."""
    caplog.set_level(logging.WARNING, logger="redsun")

    build(MisspeltApp)

    assert "panel.pause" in caplog.text
    assert "'Ctrl+Period'" in caplog.text


def test_the_dialog_lists_every_binding_by_group(
    qapp: QApplication, build: BuildSession
) -> None:
    """List window keys under Window and a view's own keys under that view, in native text."""
    dialog = opened(build(KeysApp))

    combo = dialog.findChild(QComboBox)
    assert combo is not None
    assert [combo.itemText(i) for i in range(combo.count())] == ["Window", "panel"]
    assert rows(dialog, "Window") == [["Run", native("Ctrl+R"), "", ""]]
    assert rows(dialog, "panel") == [["Refresh", native("F5"), "", ""]]


def test_an_unbound_command_is_listed_as_unbound(
    qapp: QApplication, build: BuildSession
) -> None:
    """List a command left without a key, rather than leaving it out."""
    dialog = opened(build(KeysApp, {"shortcuts": {"panel.refresh": None}}))

    assert rows(dialog, "panel") == [["Refresh", "unbound", "", ""]]


def test_a_shadowing_view_key_is_marked(
    qapp: QApplication, build: BuildSession
) -> None:
    """Mark a view key on a window key's combination, in both rows."""
    dialog = opened(build(ShadowApp))

    assert rows(dialog, "Window")[0][3] == "shadowed in shadow"
    assert rows(dialog, "shadow") == [["Run here", native("Ctrl+R"), "", "shadows Run"]]


def test_a_session_with_shortcuts_and_no_dock_has_the_window_menu(
    qapp: QApplication, build: BuildSession
) -> None:
    """Show the Window menu with Keyboard shortcuts when no view is a dock."""
    app = build(CentralOnlyApp)

    menu = app.main_window.findChild(QModelMenu, WINDOW_MENU)

    assert isinstance(menu, QModelMenu)
    assert "Keyboard shortcuts" in [a.text() for a in menu.actions()]


def test_a_view_key_wins_inside_its_view_and_the_window_key_elsewhere(
    qapp: QApplication, build: BuildSession
) -> None:
    """Run the view's command for a shared key inside the view, and the window's outside it."""
    window_ran: list[str] = []
    view_ran: list[str] = []
    app = build(
        ShadowApp,
        {"views": {"panel": {"ran": window_ran}, "shadow": {"ran": view_ran}}},
    )
    panel, shadow = app.views["panel"], app.views["shadow"]
    assert isinstance(panel, Panel)
    assert isinstance(shadow, Shadow)

    key_click(shadow.edit, QtNamespace.Key.Key_R, CTRL)
    key_click(panel.edit, QtNamespace.Key.Key_R, CTRL)

    assert view_ran == ["here"]
    assert window_ran == ["run"]


def test_a_key_qt_binds_as_nothing_is_refused(
    qapp: QApplication, build: BuildSession
) -> None:
    """Refuse a session file key app-model reads but Qt binds to nothing, naming the command."""
    with pytest.raises(ConfigurationError, match=r"shortcuts\.panel\.run"):
        build(KeysApp, {"shortcuts": {"panel.run": "PageUp"}})


def test_an_action_keeps_its_key_in_its_menu(
    qapp: QApplication, build: BuildSession
) -> None:
    """Show a session file action's settled key beside its menu entry."""
    action = {
        "id": "keys.tool",
        "title": "Tool",
        "callback": "mock_bundle.menu_callbacks:note",
        "menus": [{"id": WINDOW_MENU}],
        "keybindings": [{"primary": "F9"}],
    }
    app = build(KeysApp, {"actions": [action]})
    menu = app.main_window.findChild(QModelMenu, WINDOW_MENU)
    assert isinstance(menu, QModelMenu)

    entry = menu.findAction("keys.tool")

    assert isinstance(entry, QAction)
    assert entry.shortcut().toString() == "F9"


def test_a_disabled_action_does_not_run_from_its_key(
    qapp: QApplication, build: BuildSession, executed: list[str]
) -> None:
    """Leave a disabled session file action idle when its key is pressed."""
    action = {
        "id": "keys.idle",
        "title": "Idle",
        "callback": "mock_bundle.menu_callbacks:note",
        "menus": [{"id": WINDOW_MENU}],
        "enablement": "False",
        "keybindings": [{"primary": "F9"}],
    }
    app = build(
        RecordingApp,
        {"actions": [action], "presenters": {"recorder": {"record": executed}}},
    )
    other = app.views["other"]
    assert isinstance(other, Other)

    key_click(other.edit, QtNamespace.Key.Key_F9)

    assert executed == []


def test_the_section_gives_a_key_to_an_action_without_one(
    qapp: QApplication, build: BuildSession, caplog: pytest.LogCaptureFixture
) -> None:
    """Give a session file action a key from the shortcuts section, though it declares none."""
    caplog.set_level(logging.WARNING, logger="redsun")
    action = {
        "id": "keys.plain",
        "title": "Plain",
        "callback": "mock_bundle.menu_callbacks:note",
    }

    app = build(KeysApp, {"actions": [action], "shortcuts": {"keys.plain": "F8"}})

    assert app.model.keybindings.get_keybinding("keys.plain") is not None
    assert "no such command" not in caplog.text


def test_a_command_id_taken_by_an_action_is_logged(
    qapp: QApplication, build: BuildSession, caplog: pytest.LogCaptureFixture
) -> None:
    """Keep building when a component's command id is an action's, and name it in the log."""
    caplog.set_level(logging.WARNING, logger="redsun")
    action = {
        "id": "panel.run",
        "title": "Run",
        "callback": "mock_bundle.menu_callbacks:note",
    }

    build(KeysApp, {"actions": [action]})

    assert "panel.run" in caplog.text


def test_a_view_key_of_a_menu_entry_is_listed_unbound(
    qapp: QApplication, build: BuildSession
) -> None:
    """List a view key a menu-entry view declares as unbound, since it has no view to focus."""
    dialog = opened(build(MenuThingApp))

    assert rows(dialog, "thing") == [["Thing", "unbound", "", ""]]


def test_a_view_key_acts_only_while_its_condition_holds(
    qapp: QApplication, build: BuildSession
) -> None:
    """Leave Left to the tree while the view is not ready, and run the key once it is."""
    ran: list[str] = []
    app = build(TreeApp, {"views": {"tree": {"ran": ran}}})
    tree, other = app.views["tree"], app.views["other"]
    assert isinstance(tree, Tree)
    assert isinstance(other, Other)

    key_click(tree.tree, QtNamespace.Key.Key_Left)
    collapsed = not tree.top.isExpanded()
    tree.ready = True
    key_click(other.edit, QtNamespace.Key.Key_Escape)
    key_click(tree.tree, QtNamespace.Key.Key_Left)

    assert collapsed
    assert ran == ["back"]


def test_a_condition_that_raises_is_logged_once_and_leaves_the_key_off(
    qapp: QApplication, build: BuildSession, caplog: pytest.LogCaptureFixture
) -> None:
    """Log a condition that raises once, and leave Left to the tree."""
    ran: list[str] = []
    app = build(TreeApp, {"views": {"tree": {"ran": ran, "broken": True}}})
    tree, other = app.views["tree"], app.views["other"]
    assert isinstance(tree, Tree)
    assert isinstance(other, Other)

    with caplog.at_level(logging.ERROR, logger="redsun"):
        key_click(tree.tree, QtNamespace.Key.Key_Left)
        key_click(other.edit, QtNamespace.Key.Key_Escape)
        key_click(tree.tree, QtNamespace.Key.Key_Left)

    assert ran == []
    assert not tree.top.isExpanded()
    assert [r.getMessage() for r in caplog.records].count(
        "tree.back: its condition raised, so its key stays off"
    ) == 1


def test_a_view_key_that_is_off_still_keeps_the_window_key_out_of_its_view(
    qapp: QApplication, build: BuildSession
) -> None:
    """Give Left to the focused tree, not to the window's key, while the view's key is off."""
    ran: list[str] = []
    app = build(
        TreeWalkerApp, {"views": {"tree": {"ran": ran}, "walker": {"ran": ran}}}
    )
    tree = app.views["tree"]
    assert isinstance(tree, Tree)

    key_click(tree.tree, QtNamespace.Key.Key_Left)

    assert ran == []
    assert not tree.top.isExpanded()


def test_a_saved_key_moves_a_command_at_once_and_a_reset_moves_it_back(
    qapp: QApplication, build: BuildSession
) -> None:
    """Run a command from its new key and not its old one, and from the old one after a reset."""
    ran: list[str] = []
    app = build(KeysApp, {"views": {"panel": {"ran": ran}}})
    other = app.views["other"]
    assert isinstance(other, Other)

    app.set_shortcuts({"panel.run": ["F9"]})
    key_click(other.edit, QtNamespace.Key.Key_R, CTRL)
    after_old = list(ran)
    key_click(other.edit, QtNamespace.Key.Key_F9)
    after_new = list(ran)
    app.reset_shortcuts()
    key_click(other.edit, QtNamespace.Key.Key_F9)
    key_click(other.edit, QtNamespace.Key.Key_R, CTRL)

    assert (after_old, after_new, ran) == ([], ["run"], ["run", "run"])


def test_a_saved_key_moves_a_session_file_action_in_the_registry(
    qapp: QApplication, build: BuildSession
) -> None:
    """Give a session file action its saved key in the keybinding registry, dropping the old one."""
    action = {
        "id": "keys.plain",
        "title": "Plain",
        "callback": "mock_bundle.menu_callbacks:note",
    }
    app = build(KeysApp, {"actions": [action], "shortcuts": {"keys.plain": "F8"}})

    app.set_shortcuts({"keys.plain": ["F9"]})
    moved = app.model.keybindings.get_keybinding("keys.plain")
    app.set_shortcuts({"keys.plain": []})

    assert moved is not None
    assert str(moved.keybinding) == "F9"
    assert app.model.keybindings.get_keybinding("keys.plain") is None


def test_an_edited_view_key_still_wins_inside_its_view(
    qapp: QApplication, build: BuildSession
) -> None:
    """Keep a view key moved onto the window's key winning while its view has focus."""
    ran: list[str] = []
    app = build(KeysApp, {"views": {"panel": {"ran": ran}}})
    panel, other = app.views["panel"], app.views["other"]
    assert isinstance(panel, Panel)
    assert isinstance(other, Other)

    app.set_shortcuts({"panel.refresh": ["Ctrl+R"]})
    key_click(panel.edit, QtNamespace.Key.Key_R, CTRL)
    key_click(other.edit, QtNamespace.Key.Key_R, CTRL)

    assert ran == ["refresh", "run"]


def test_the_open_list_shows_a_saved_key(
    qapp: QApplication, build: BuildSession
) -> None:
    """Show a key saved while the list is open."""
    app = build(KeysApp)
    dialog = opened(app)

    app.set_shortcuts({"panel.run": ["F9"]})

    assert rows(dialog, "Window")[0][1] == native("F9")
