"""Helpers the view tests share."""

from __future__ import annotations

from typing import TypeVar

from qtpy import QtCore, QtGui, QtWidgets

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
