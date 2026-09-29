"""Tests for the dialog showing a plan's documentation."""

from __future__ import annotations

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

    def accept() -> None:
        dialog = qapp.activeModalWidget()
        # closed whatever it is, so a wrong dialog fails the test, not hangs it
        if isinstance(dialog, PlanInfoDialog):
            seen.append((dialog.windowTitle(), dialog.text_edit.toPlainText()))
            dialog.ok_button.click()
        elif isinstance(dialog, QtWidgets.QDialog):
            dialog.reject()

    QtCore.QTimer.singleShot(0, accept)

    result = PlanInfoDialog.show_dialog("Plan information", "**Scan** a region")

    assert result == QtWidgets.QDialog.DialogCode.Accepted
    assert seen == [("Plan information", "Scan a region")]
