"""Tests for the keyboard shortcuts a Qt session binds and lists."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, ClassVar, cast

import pytest
from qtpy.QtCore import Qt as QtNamespace
from qtpy.QtGui import QAction
from qtpy.QtTest import QTest
from qtpy.QtWidgets import QApplication, QLineEdit, QVBoxLayout, QWidget

from redsun import AsView, Placement, shortcut
from redsun.qt import Dock, QtSession

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


def press(widget: QWidget, key: QtNamespace.Key, modifier: Any = None) -> None:
    """Focus *widget* in its shown, active window and press *key* there."""
    window = widget.window()
    assert window is not None
    window.show()
    window.activateWindow()
    widget.setFocus()
    QApplication.processEvents()
    # pyqt6's stubs type QTest's static methods as instance methods
    test = cast("Any", QTest)
    if modifier is None:
        test.keyClick(widget, key)
    else:
        test.keyClick(widget, key, modifier)


def test_a_window_key_runs_its_method_from_anywhere(
    qapp: QApplication, build: BuildSession
) -> None:
    """Run a window key's method with focus in another view."""
    ran: list[str] = []
    app = build(KeysApp, {"views": {"panel": {"ran": ran}}})
    other = app.views["other"]
    assert isinstance(other, Other)

    press(other.edit, QtNamespace.Key.Key_R, CTRL)

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

    press(other.edit, QtNamespace.Key.Key_F5)
    press(panel.edit, QtNamespace.Key.Key_F5)

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

    press(other.edit, QtNamespace.Key.Key_R, CTRL)

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
