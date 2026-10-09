"""Helpers the view tests share."""

from __future__ import annotations

from typing import Any, TypeVar, cast

from qtpy import QtCore, QtGui, QtWidgets
from qtpy.QtTest import QTest

T = TypeVar("T", bound=QtCore.QObject)


def child(parent: QtCore.QObject, kind: type[T], name: str = "") -> T:
    """Return the child of *parent* of type *kind*, named *name* when given."""
    found = parent.findChild(kind, name) if name else parent.findChild(kind)
    assert found is not None
    return found


def press(widget: QtWidgets.QWidget, *keys: str | QtCore.Qt.Key) -> None:
    """Press and release each of *keys* on *widget*: a character or a named key."""
    for key in keys:
        code, text = (0, key) if isinstance(key, str) else (key, "")
        for kind in (QtCore.QEvent.Type.KeyPress, QtCore.QEvent.Type.KeyRelease):
            event = QtGui.QKeyEvent(
                kind, code, QtCore.Qt.KeyboardModifier.NoModifier, text
            )
            QtWidgets.QApplication.sendEvent(widget, event)


def type_into(edit: QtWidgets.QLineEdit, text: str) -> None:
    """Replace the text of *edit* by typing *text*, then press Enter."""
    edit.selectAll()
    press(edit, *text, QtCore.Qt.Key.Key_Return)


def key_click(
    widget: QtWidgets.QWidget, key: QtCore.Qt.Key, modifier: Any = None
) -> None:
    """Focus *widget* in its shown, active window and press *key* there, shortcuts included."""
    window = widget.window()
    assert window is not None
    window.show()
    window.activateWindow()
    widget.setFocus()
    QtWidgets.QApplication.processEvents()
    # pyqt6's stubs type QTest's static methods as instance methods
    test = cast("Any", QTest)
    if modifier is None:
        test.keyClick(widget, key)
    else:
        test.keyClick(widget, key, modifier)
