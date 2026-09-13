from __future__ import annotations

import logging
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING

from qtpy import QtCore, QtGui
from qtpy import QtWidgets as QtW

from redsun.log import GlobalFormatter, log_buffer, session_log
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

# TODO: the level colours are fixed, two sets picked by background lightness;
# a palette with its own colours for log levels could supply them instead
_ON_LIGHT: dict[int, str] = {
    logging.DEBUG: "#5c5c5c",
    logging.INFO: "#0b3d91",
    logging.WARNING: "#8a4b00",
    logging.ERROR: "#b3261e",
    logging.CRITICAL: "#7b1fa2",
}
"""Level colours for a light console, each at least 6:1 against white."""

_ON_DARK: dict[int, str] = {
    logging.DEBUG: "#b0b0b0",
    logging.INFO: "#9ecbff",
    logging.WARNING: "#ffb95c",
    logging.ERROR: "#ff8a80",
    logging.CRITICAL: "#e0a3ff",
}
"""Level colours for a dark console, each at least 6:1 against near-black."""

_MID_LIGHTNESS = 128
"""Above this the console background counts as light."""

_BATCH_INTERVAL_MS = 100
"""How often records that arrived since the last batch are drawn."""

_BATCH_SIZE = 2_000
"""The most records one batch draws; the rest wait for the next."""


class LogView(QtView):
    """Read-only console showing the log records of the running session.

    Records emitted before this view existed are shown too: the session buffer
    outlives them, and the view drains it on construction. The level selector
    chooses the lowest level displayed, and re-reading the buffer rather than
    the text edit means raising the threshold and lowering it again brings
    records back.

    A record is coloured by its level, in one of two sets chosen from the
    console's own background, so the text stays legible under a light and a
    dark palette alike. Changing the palette while the view is open redraws
    it.

    Records arriving while the view is open are drawn in batches rather than
    one by one, so a burst of logging does not stall the window, and the
    console keeps no more lines than the session buffer holds records.

    When the session has a log file open, ``Save logs...`` copies it and
    ``Open log folder`` shows the folder holding it in the system's file
    browser; without one the folder button is disabled.

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

        buffer = log_buffer()

        self._console = QtW.QPlainTextEdit(self)
        self._console.setReadOnly(True)
        self._console.setMaximumBlockCount(buffer.capacity)
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
        self._folder_button = QtW.QPushButton("Open log folder", self)
        self._folder_button.clicked.connect(self._on_folder_clicked)
        handler = session_log()
        self._folder_button.setEnabled(handler is not None)
        if handler is not None:
            self._folder_button.setToolTip(str(Path(handler.baseFilename).parent))

        root = QtW.QGridLayout(self)
        root.addWidget(self._console, 0, 0, 1, 4)
        root.addWidget(QtW.QLabel("Level:", self), 1, 0)
        root.addWidget(self._level_combo, 1, 1, 1, 3)
        root.addWidget(self._save_button, 2, 1)
        root.addWidget(self._clear_button, 2, 2)
        root.addWidget(self._folder_button, 2, 3)
        # the label column keeps its own width; the three that carry the
        # buttons share the rest evenly, so the combo box spans exactly them
        for column in (1, 2, 3):
            root.setColumnStretch(column, 1)
        self.setLayout(root)

        # only the newest records can end up on screen, so a burst larger
        # than the buffer never queues more than the console would keep
        self._pending: deque[logging.LogRecord] = deque(maxlen=buffer.capacity)
        self._batch_timer = QtCore.QTimer(self)
        self._batch_timer.setInterval(_BATCH_INTERVAL_MS)
        self._batch_timer.timeout.connect(self._draw_batch)

        self._render(buffer.records)
        # psygnal holds the bound method weakly, so a destroyed view drops out
        # of the buffer on its own: a view is never asked to shut down
        buffer.sig_record.connect(self._on_record, thread="main")

    def changeEvent(self, event: QtCore.QEvent | None) -> None:
        """Redraw in the colours of the palette the console now carries."""
        if event is not None:
            super().changeEvent(event)
            if event.type() == QtCore.QEvent.Type.PaletteChange:
                self._render(log_buffer().records)

    def closeEvent(self, event: QtGui.QCloseEvent | None) -> None:
        """Stop following the buffer once the console is closed."""
        log_buffer().sig_record.disconnect(self._on_record, missing_ok=True)
        self._batch_timer.stop()
        self._pending.clear()
        if event is not None:
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
        self._pending.clear()
        self._console.clear()

    def save(self, path: str) -> None:
        """Write this run's records to *path*, whatever the displayed level.

        The records come from the session's log file when a session opened
        one, so nothing the buffer has already dropped is missing, and from the
        buffer otherwise.
        """
        handler = session_log()
        with open(path, "w", encoding="utf-8") as fh:
            if handler is None:
                fh.writelines(
                    f"{self._formatter.format(record)}\n"
                    for record in log_buffer().records
                )
                return
            handler.flush()
            fh.writelines(
                source.read_text(encoding="utf-8") for source in handler.files
            )

    def _on_record(self, record: logging.LogRecord) -> None:
        if record.levelno < self._level:
            return
        self._pending.append(record)
        if not self._batch_timer.isActive():
            self._batch_timer.start()

    def _draw_batch(self) -> None:
        count = min(_BATCH_SIZE, len(self._pending))
        self._write([self._pending.popleft() for _ in range(count)])
        if not self._pending:
            self._batch_timer.stop()

    def _render(self, records: Iterable[logging.LogRecord]) -> None:
        self._batch_timer.stop()
        self._pending.clear()
        self._console.clear()
        self._write([record for record in records if record.levelno >= self._level])

    @property
    def colors(self) -> dict[int, str]:
        """The level colours in use, chosen from the console's background."""
        base = self._console.palette().color(QtGui.QPalette.ColorRole.Base)
        return _ON_LIGHT if base.lightness() >= _MID_LIGHTNESS else _ON_DARK

    def _write(self, records: Iterable[logging.LogRecord]) -> None:
        # pyqt6 annotates both as optional and pyside6 does not
        document: QtGui.QTextDocument | None = self._console.document()
        bar: QtW.QScrollBar | None = self._console.verticalScrollBar()
        if document is None or bar is None:
            return
        # follow the newest line only when the reader is already at the bottom
        following = bar.value() == bar.maximum()
        colors = self.colors
        formats: dict[int, QtGui.QTextCharFormat] = {}
        cursor = QtGui.QTextCursor(document)
        cursor.movePosition(QtGui.QTextCursor.MoveOperation.End)
        cursor.beginEditBlock()
        for record in records:
            if record.levelno not in formats:
                char_format = QtGui.QTextCharFormat()
                color = colors.get(record.levelno, colors[logging.INFO])
                char_format.setForeground(QtGui.QBrush(QtGui.QColor(color)))
                formats[record.levelno] = char_format
            if not document.isEmpty():
                cursor.insertBlock()
            cursor.insertText(self._formatter.format(record), formats[record.levelno])
        cursor.endEditBlock()
        if following:
            bar.setValue(bar.maximum())

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

    def _on_folder_clicked(self) -> None:
        handler = session_log()
        if handler is None:
            return
        folder = Path(handler.baseFilename).parent
        if not QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(folder))):
            QtW.QMessageBox.warning(self, "Could not open the log folder", str(folder))
