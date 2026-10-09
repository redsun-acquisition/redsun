"""A list of the keyboard shortcuts a session binds, by where they act."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qtpy.QtGui import QKeySequence, QPalette
from qtpy.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ...session._shortcuts import Binding

__all__ = ["ShortcutsDialog"]

WINDOW = "Window"
"""The group of the keys that act anywhere in the window."""

COLUMNS = ("Command", "Key", "Second key", "Note")
"""The table's headings."""


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
    """Lists the keys a session binds: those of the whole window, then each view's own."""

    def __init__(
        self, bindings: Sequence[Binding], parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Keyboard shortcuts")
        self._bindings = list(bindings)
        self._notes = notes(self._bindings)
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
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close)
        layout = QVBoxLayout(self)
        layout.addWidget(self._groups)
        layout.addWidget(self._table)
        layout.addWidget(buttons)
        self._groups.currentTextChanged.connect(self._show_group)
        self._show_group(WINDOW)

    def set_bindings(self, bindings: Sequence[Binding]) -> None:
        """Show *bindings* in place of those shown, keeping the group chosen."""
        self._bindings = list(bindings)
        self._notes = notes(self._bindings)
        self._show_group(self._groups.currentText())

    def _show_group(self, group: str) -> None:
        """Fill the table with the bindings of *group*."""
        view = None if group == WINDOW else group
        shown = [b for b in self._bindings if b.view == view]
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
