"""A list of the keyboard shortcuts a session binds, by where they act."""

from __future__ import annotations

from functools import partial
from typing import TYPE_CHECKING

from app_model.backends.qt import qkeysequence2modelkeybinding
from qtpy.QtGui import QKeySequence, QPalette
from qtpy.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QKeySequenceEdit,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...session._shortcuts import holder

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from ...session._shortcuts import Binding

__all__ = ["ShortcutsDialog"]

WINDOW = "Window"
"""The group of the keys that act anywhere in the window."""

COLUMNS = ("Command", "Key", "Second key", "Note")
"""The table's headings."""

CLEARING = frozenset({"Backspace", "Delete"})
"""Keys that, pressed alone in a key cell, clear it."""


def native(key: str) -> str:
    """Return *key* as the platform writes it, such as ⌘R on macOS."""
    return QKeySequence(key).toString(QKeySequence.SequenceFormat.NativeText)


def notes(bindings: Sequence[Binding]) -> dict[str, str]:
    """Return, by command, what a view key shadowing a window key says, on both sides."""
    window = {key: b for b in bindings if b.view is None for key in b.keys}
    said: dict[str, str] = {}
    for binding in bindings:
        if binding.view is None:
            continue
        for key in binding.keys:
            if (shadowed := window.get(key)) is not None:
                said[binding.command] = f"shadows {shadowed.title}"
                said[shadowed.command] = f"shadowed in {binding.view}"
    return said


class ShortcutsDialog(QDialog):
    """Lists the keys a session binds, those of the whole window then each view's own, and edits them.

    Double-click a key cell and press the new key; Backspace or Delete clears
    it. A key another command holds in the same place is moved after the user
    agrees. *change* receives the new keys by command and raises `ValueError`
    for a key it refuses; *reset* forgets every change.
    """

    def __init__(
        self,
        bindings: Sequence[Binding],
        change: Callable[[dict[str, tuple[str, ...]]], None],
        reset: Callable[[], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Keyboard shortcuts")
        self._bindings = list(bindings)
        self._notes = notes(self._bindings)
        self._change = change
        self._shown: list[Binding] = []
        self._groups = QComboBox()
        views = dict.fromkeys(b.view for b in self._bindings if b.view is not None)
        self._groups.addItems([WINDOW, *views])
        self._table = QTableWidget(0, len(COLUMNS))
        self._table.setHorizontalHeaderLabels(COLUMNS)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        if (rows := self._table.verticalHeader()) is not None:
            rows.setVisible(False)
        if (columns := self._table.horizontalHeader()) is not None:
            columns.setStretchLastSection(True)
        self._table.cellDoubleClicked.connect(self._edit)
        self._problem = QLabel()
        self._problem.setObjectName("shortcut-problem")
        self._problem.setWordWrap(True)
        reset_button = QPushButton("Reset to defaults")
        reset_button.setObjectName("reset-shortcuts")
        reset_button.clicked.connect(reset)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close)
        bottom = QHBoxLayout()
        bottom.addWidget(reset_button)
        bottom.addStretch(1)
        bottom.addWidget(buttons)
        layout = QVBoxLayout(self)
        layout.addWidget(self._groups)
        layout.addWidget(self._table)
        layout.addWidget(self._problem)
        layout.addLayout(bottom)
        self._groups.currentTextChanged.connect(self._show_group)
        self._show_group(WINDOW)

    def set_bindings(self, bindings: Sequence[Binding]) -> None:
        """Show *bindings* in place of those shown, keeping the group chosen."""
        self._bindings = list(bindings)
        self._notes = notes(self._bindings)
        self._show_group(self._groups.currentText())

    def _show_group(self, group: str) -> None:
        """Fill the table with the bindings of *group*."""
        for row in range(self._table.rowCount()):
            for column in (1, 2):
                self._table.removeCellWidget(row, column)
        view = None if group == WINDOW else group
        shown = [b for b in self._bindings if b.view == view]
        self._shown = shown
        self._table.setRowCount(len(shown))
        for row, binding in enumerate(shown):
            keys = [native(key) for key in binding.keys]
            cells = [
                binding.title,
                keys[0] if keys else "unbound",
                keys[1] if len(keys) > 1 else "",
                self._notes.get(binding.command, ""),
            ]
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if column == 1 and not keys:
                    item.setForeground(
                        self.palette().color(QPalette.ColorRole.PlaceholderText)
                    )
                self._table.setItem(row, column, item)
        self._table.resizeColumnsToContents()

    def _edit(self, row: int, column: int) -> None:
        """Open a key editor in a key cell of *row*."""
        if column not in (1, 2) or row >= len(self._shown):
            return
        editor = QKeySequenceEdit(self._table)
        editor.setMaximumSequenceLength(1)
        editor.editingFinished.connect(partial(self._captured, row, column, editor))
        self._table.setCellWidget(row, column, editor)
        editor.setFocus()

    def _captured(self, row: int, column: int, editor: QKeySequenceEdit) -> None:
        """Turn the key pressed in *editor* into a change, asking first if it is taken."""
        # the editor finishes again when a prompt takes its focus
        editor.editingFinished.disconnect()
        sequence = editor.keySequence()
        self._table.removeCellWidget(row, column)
        if sequence.isEmpty():
            return
        binding = self._shown[row]
        key = str(qkeysequence2modelkeybinding(sequence))
        keys = list(binding.keys)
        index = column - 1
        if key in CLEARING:
            if index < len(keys):
                del keys[index]
        elif index < len(keys):
            keys[index] = key
        else:
            keys.append(key)
        if tuple(dict.fromkeys(keys)) == binding.keys:
            return
        changes = {binding.command: tuple(dict.fromkeys(keys))}
        other = None if key in CLEARING else holder(self._bindings, binding, key)
        if other is not None:
            if not self._agree(f"Already used by {other.title}; move it here?"):
                return
            changes[other.command] = tuple(k for k in other.keys if k != key)
        try:
            self._change(changes)
        except ValueError as error:
            self._problem.setText(str(error))
            return
        self._problem.clear()

    def _agree(self, question: str) -> bool:
        """Ask *question*, and return whether the user said yes."""
        prompt = QMessageBox(self)
        prompt.setWindowTitle("Keyboard shortcuts")
        prompt.setText(question)
        prompt.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        prompt.setDefaultButton(QMessageBox.StandardButton.No)
        return prompt.exec() == QMessageBox.StandardButton.Yes
