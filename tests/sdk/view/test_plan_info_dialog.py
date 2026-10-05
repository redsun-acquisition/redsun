"""Tests for the dialog showing a plan's documentation."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import pytest
from qtpy import QtCore, QtWidgets

from redsun.view.qt.utils import PlanInfoDialog

if TYPE_CHECKING:
    from qtpy.QtWidgets import QApplication

pytestmark = pytest.mark.qt


def test_the_dialog_renders_markdown_and_returns_once_accepted(
    qapp: QApplication,
) -> None:
    """Render the Markdown text and return `Accepted` once OK is clicked."""
    seen: list[tuple[str, str]] = []
    deadline = time.perf_counter() + 5
    timer = QtCore.QTimer()
    timer.setInterval(10)

    def accept() -> None:
        dialog = qapp.activeModalWidget()
        if isinstance(dialog, PlanInfoDialog):
            timer.stop()
            seen.append((dialog.windowTitle(), dialog.text_edit.toPlainText()))
            dialog.ok_button.click()
        elif isinstance(dialog, QtWidgets.QDialog):
            timer.stop()
            dialog.reject()
        elif time.perf_counter() > deadline:
            timer.stop()
            for widget in qapp.topLevelWidgets():
                if isinstance(widget, QtWidgets.QDialog):
                    widget.reject()

    timer.timeout.connect(accept)
    timer.start()

    result = PlanInfoDialog.show_dialog("Plan information", "**Scan** a region")

    assert result == QtWidgets.QDialog.DialogCode.Accepted
    assert seen == [("Plan information", "Scan a region")]
