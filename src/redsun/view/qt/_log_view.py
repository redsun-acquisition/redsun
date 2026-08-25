from __future__ import annotations

import html
import logging
from typing import TYPE_CHECKING

from qtpy import QtGui
from qtpy import QtWidgets as QtW

from redsun.log import GlobalFormatter, log_buffer
from redsun.view import ViewPosition
from redsun.view.qt import QtView

if TYPE_CHECKING:
    from collections.abc import Iterable
    from typing import Any

__all__ = ["LogView"]

_LEVELS: tuple[tuple[str, int], ...] = (
    ("DEBUG", logging.DEBUG),
    ("INFO", logging.INFO),
    ("WARNING", logging.WARNING),
    ("ERROR", logging.ERROR),
    ("CRITICAL", logging.CRITICAL),
)

_COLORS: dict[int, str] = {
    logging.DEBUG: "gray",
    logging.INFO: "blue",
    logging.WARNING: "orange",
    logging.ERROR: "red",
    logging.CRITICAL: "purple",
}


class LogView(QtView):
    """Read-only console showing the log records of the running session.

    Records emitted before this view existed are shown too: the session buffer
    outlives them, and the view drains it on construction. The level selector
    chooses the lowest level displayed, and re-reading the buffer rather than
    the text edit means raising the threshold and lowering it again brings
    records back.

    Parameters
    ----------
    name : str
        Identity key of the view. Passed as positional-only argument.
    kwargs : Any, optional
        Additional keyword arguments (unused).
    """

    @property
    def view_position(self) -> ViewPosition:
        """The position in the main view."""
        return ViewPosition.BOTTOM

    def __init__(self, name: str, /, **kwargs: Any) -> None:
        super().__init__(name, **kwargs)

        self._formatter = GlobalFormatter(datefmt="%d-%m-%y|%H:%M:%S")
        self._level = logging.INFO

        self._console = QtW.QPlainTextEdit(self)
        self._console.setReadOnly(True)
        font = QtGui.QFont("nosuchfont")
        font.setStyleHint(QtGui.QFont.StyleHint.Monospace)
        self._console.setFont(font)

        self._level_combo = QtW.QComboBox(self)
        for label, level in _LEVELS:
            self._level_combo.addItem(label, level)
        self._level_combo.setCurrentIndex(self._level_combo.findData(self._level))
        self._level_combo.currentIndexChanged.connect(self._on_level_selected)

        self._save_button = QtW.QPushButton("Save logs...", self)
        self._save_button.clicked.connect(self._on_save_clicked)
        self._clear_button = QtW.QPushButton("Clear log window", self)
        self._clear_button.clicked.connect(self.clear)

        root = QtW.QGridLayout(self)
        root.addWidget(self._console, 0, 0, 1, 3)
        root.addWidget(QtW.QLabel("Level:", self), 1, 0)
        root.addWidget(self._level_combo, 1, 1, 1, 2)
        root.addWidget(self._save_button, 2, 1)
        root.addWidget(self._clear_button, 2, 2)
        # the label column keeps its own width; the two that carry the buttons
        # share the rest evenly, so the combo box spans exactly both of them
        root.setColumnStretch(1, 1)
        root.setColumnStretch(2, 1)
        self.setLayout(root)

        buffer = log_buffer()
        self._render(buffer.records)
        # psygnal holds the bound method weakly, so a destroyed view drops out
        # of the buffer on its own: a view is never asked to shut down
        buffer.sig_record.connect(self._on_record, thread="main")

    def closeEvent(self, event: QtGui.QCloseEvent | None) -> None:
        """Stop following the buffer once the console is closed."""
        log_buffer().sig_record.disconnect(self._on_record, missing_ok=True)
        super().closeEvent(event)

    @property
    def level(self) -> int:
        """The lowest level currently displayed."""
        return self._level

    def set_level(self, level: int) -> None:
        """Show only records at or above *level*, redrawing from the buffer."""
        self._level = level
        index = self._level_combo.findData(level)
        if index != -1 and index != self._level_combo.currentIndex():
            # the selection change comes back through _on_level_selected,
            # which renders once the combo agrees with the level
            self._level_combo.setCurrentIndex(index)
            return
        self._render(log_buffer().records)

    def _on_level_selected(self, index: int) -> None:
        self.set_level(int(self._level_combo.itemData(index)))

    def clear(self) -> None:
        """Empty the console.

        The session buffer is untouched, so a later ``Save logs...`` still
        writes everything and changing level brings the records back.
        """
        self._console.clear()

    def save(self, path: str) -> None:
        """Write every buffered record to *path*, whatever the displayed level."""
        with open(path, "w", encoding="utf-8") as fh:
            fh.writelines(
                f"{self._formatter.format(record)}\n" for record in log_buffer().records
            )

    def _on_record(self, record: logging.LogRecord) -> None:
        if record.levelno >= self._level:
            self._append(record)

    def _render(self, records: Iterable[logging.LogRecord]) -> None:
        self._console.clear()
        for record in records:
            if record.levelno >= self._level:
                self._append(record)

    def _append(self, record: logging.LogRecord) -> None:
        color = _COLORS.get(record.levelno, "black")
        text = html.escape(self._formatter.format(record))
        self._console.appendHtml(f'<pre><font color="{color}">{text}</font></pre>')

    def _on_save_clicked(self) -> None:
        chosen, _ = QtW.QFileDialog.getSaveFileName(
            self, "Save session logs", "redsun.log", "Log files (*.log);;All files (*)"
        )
        if not chosen:
            return
        try:
            self.save(chosen)
        except OSError as e:
            QtW.QMessageBox.warning(self, "Could not save logs", str(e))
