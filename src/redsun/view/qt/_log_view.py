from __future__ import annotations

import logging
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING

from qtpy import QtCore, QtGui
from qtpy import QtWidgets as QtW

from redsun.log import GlobalFormatter, log_buffer, service_of, session_log
from redsun.qt import Dock

if TYPE_CHECKING:
    from collections.abc import Iterable

    from redsun.view import Placement

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
"""The most records one batch draws on each console; the rest wait for the next."""

_SERVICES_TAB = 1
"""Index of the Services tab."""

_ALL_SERVICES = "All services"
"""Selector entry showing the records of every service."""


class LogView(QtW.QWidget):
    """Read-only console of the running session's log records.

    Records logged before the view existed are shown too, read from the session
    buffer. The level selector sets the lowest level shown; since the view
    redraws from the buffer, lowering the level again brings records back.

    Application and service records have their own tabs. The Services tab
    appears once a service logs, and its selector narrows it to one service.
    ``Clear log window`` and ``Save logs...`` act on the tab and service shown.

    Records are coloured by level, with one palette for light and one for dark
    backgrounds, chosen from the console's background and redrawn when the
    palette changes.

    New records are drawn in batches, so a burst does not stall the window, and
    each console keeps no more lines than the buffer holds for it.

    With session log files open, ``Save logs...`` copies the files of the tab
    shown and ``Open log folder`` opens their folder in the file browser;
    without them the folder button is disabled.
    """

    placement: Placement = Dock("bottom")
    """Docked at the bottom of the main window."""

    def __init__(self, name: str, parent: QtW.QWidget) -> None:
        super().__init__(parent)
        self.name = name

        self._formatter = GlobalFormatter(datefmt="%d-%m-%y|%H:%M:%S")
        self._level = logging.INFO

        buffer = log_buffer()

        self._console = self._make_console(buffer.capacity)
        self._service_console = self._make_console(buffer.service_capacity)
        self._service_combo = QtW.QComboBox(self)
        self._service_combo.addItem(_ALL_SERVICES, None)
        services_page = QtW.QWidget(self)
        services_layout = QtW.QVBoxLayout(services_page)
        services_layout.setContentsMargins(0, 0, 0, 0)
        services_layout.addWidget(self._service_combo)
        services_layout.addWidget(self._service_console)
        self._tabs = QtW.QTabWidget(self)
        self._tabs.addTab(self._console, "Application")
        self._tabs.addTab(services_page, "Services")
        self._tabs.setTabVisible(_SERVICES_TAB, False)
        # only the newest records can end up on screen, so a burst larger than
        # the buffer never queues more than a console would keep
        self._pending: deque[logging.LogRecord] = deque(maxlen=buffer.capacity)
        self._service_pending: deque[logging.LogRecord] = deque(
            maxlen=buffer.service_capacity
        )
        for service in buffer.services:
            self._add_service(service)
        self._service_combo.currentIndexChanged.connect(self._on_service_selected)

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
        root.addWidget(self._tabs, 0, 0, 1, 4)
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

        self._batch_timer = QtCore.QTimer(self)
        self._batch_timer.setInterval(_BATCH_INTERVAL_MS)
        self._batch_timer.timeout.connect(self._draw_batch)

        self._render()
        # psygnal holds the bound method weakly, so a destroyed view drops out
        # of the buffer on its own: a view is never asked to shut down
        buffer.sig_record.connect(self._on_record, thread="main")

    def _make_console(self, capacity: int) -> QtW.QPlainTextEdit:
        console = QtW.QPlainTextEdit(self)
        console.setReadOnly(True)
        console.setMaximumBlockCount(capacity)
        font = QtGui.QFont("nosuchfont")
        font.setStyleHint(QtGui.QFont.StyleHint.Monospace)
        console.setFont(font)
        return console

    def changeEvent(self, event: QtCore.QEvent | None) -> None:
        """Redraw in the colours of the palette the console now carries."""
        if event is not None:
            super().changeEvent(event)
            if event.type() == QtCore.QEvent.Type.PaletteChange:
                self._render()

    def closeEvent(self, event: QtGui.QCloseEvent | None) -> None:
        """Stop following the buffer once the console is closed."""
        log_buffer().sig_record.disconnect(self._on_record, missing_ok=True)
        self._batch_timer.stop()
        self._pending.clear()
        self._service_pending.clear()
        if event is not None:
            super().closeEvent(event)

    @property
    def level(self) -> int:
        """The lowest level currently displayed."""
        return self._level

    @property
    def service(self) -> str | None:
        """The service the Services tab shows, ``None`` for every service."""
        data = self._service_combo.currentData()
        return None if data is None else str(data)

    def set_level(self, level: int) -> None:
        """Show only records at or above *level*, redrawing from the buffer."""
        self._level = level
        index = self._level_combo.findData(level)
        if index != -1 and index != self._level_combo.currentIndex():
            # the selection change comes back through _on_level_selected,
            # which renders once the combo agrees with the level
            self._level_combo.setCurrentIndex(index)
            return
        self._render()

    def _on_level_selected(self, index: int) -> None:
        self.set_level(int(self._level_combo.itemData(index)))

    def _on_service_selected(self, index: int) -> None:
        self._render()

    def clear(self) -> None:
        """Empty the console of the tab shown.

        The buffer is untouched, so ``Save logs...`` still writes everything and
        changing the level brings records back.
        """
        if self._tabs.currentIndex() == _SERVICES_TAB:
            self._service_pending.clear()
            self._service_console.clear()
        else:
            self._pending.clear()
            self._console.clear()

    def save(self, path: str) -> None:
        """Write the records of the tab shown to *path*, whatever the displayed level.

        The Application tab writes application records; the Services tab the
        selected service's, or every service's in turn. They come from the
        session's log files if open, so records the buffer dropped are
        included, and from the buffer otherwise.
        """
        buffer = log_buffer()
        if self._tabs.currentIndex() != _SERVICES_TAB:
            sources: list[tuple[str | None, Iterable[logging.LogRecord]]] = [
                (None, buffer.records)
            ]
        else:
            names = buffer.services if self.service is None else (self.service,)
            sources = [(name, buffer.service_records(name)) for name in names]
        with open(path, "w", encoding="utf-8") as fh:
            for source, records in sources:
                handler = session_log(source)
                if handler is None:
                    fh.writelines(
                        f"{self._formatter.format(record)}\n" for record in records
                    )
                    continue
                handler.flush()
                fh.writelines(
                    file.read_text(encoding="utf-8") for file in handler.files
                )

    def _add_service(self, service: str) -> None:
        """Offer *service* in the selector, and show the Services tab."""
        self._service_combo.addItem(service, service)
        self._tabs.setTabVisible(_SERVICES_TAB, True)
        capacity = log_buffer().service_capacity * (self._service_combo.count() - 1)
        self._service_console.setMaximumBlockCount(capacity)
        self._service_pending = deque(self._service_pending, maxlen=capacity)

    def _on_record(self, record: logging.LogRecord) -> None:
        service = service_of(record)
        if service is not None and self._service_combo.findData(service) == -1:
            self._add_service(service)
        if record.levelno < self._level:
            return
        if service is None:
            self._pending.append(record)
        elif self.service in (None, service):
            self._service_pending.append(record)
        else:
            return
        if not self._batch_timer.isActive():
            self._batch_timer.start()

    def _draw_batch(self) -> None:
        for pending, console in (
            (self._pending, self._console),
            (self._service_pending, self._service_console),
        ):
            count = min(_BATCH_SIZE, len(pending))
            self._write(console, [pending.popleft() for _ in range(count)])
        if not (self._pending or self._service_pending):
            self._batch_timer.stop()

    def _render(self) -> None:
        buffer = log_buffer()
        self._batch_timer.stop()
        self._pending.clear()
        self._service_pending.clear()
        self._console.clear()
        self._service_console.clear()
        self._write(
            self._console, [r for r in buffer.records if r.levelno >= self._level]
        )
        self._write(
            self._service_console,
            [
                r
                for r in buffer.service_records(self.service)
                if r.levelno >= self._level
            ],
        )

    @property
    def colors(self) -> dict[int, str]:
        """The level colours in use, chosen from the console's background."""
        base = self._console.palette().color(QtGui.QPalette.ColorRole.Base)
        return _ON_LIGHT if base.lightness() >= _MID_LIGHTNESS else _ON_DARK

    def _write(
        self, console: QtW.QPlainTextEdit, records: Iterable[logging.LogRecord]
    ) -> None:
        # pyqt6 annotates both as optional and pyside6 does not
        document: QtGui.QTextDocument | None = console.document()
        bar: QtW.QScrollBar | None = console.verticalScrollBar()
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
