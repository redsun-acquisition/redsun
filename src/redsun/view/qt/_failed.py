from __future__ import annotations

import traceback
from typing import TYPE_CHECKING

from qtpy.QtCore import Qt
from qtpy.QtWidgets import QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

if TYPE_CHECKING:
    from collections.abc import Mapping

    from redsun.view import Placement

__all__ = ["FailedView", "FailuresButton", "show_failures"]


def described(error: BaseException) -> str:
    """Return the traceback of *error*, or its message when it carries none."""
    return "".join(traceback.format_exception(error)).strip()


def show_failures(
    parent: QWidget | None, title: str, failures: Mapping[str, BaseException]
) -> None:
    """Show a dialog naming each failed component and its reason.

    The tracebacks are in the details of the dialog.
    """
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(title)
    box.setText(title)
    box.setInformativeText(
        "\n".join(f"{name}: {error}" for name, error in failures.items())
    )
    box.setDetailedText(
        "\n\n".join(f"{name}\n{described(error)}" for name, error in failures.items())
    )
    box.exec()


class FailedView(QWidget):
    """Stands where a view that failed to build would have been.

    It names the view and the reason, and shows the traceback on request.
    """

    def __init__(
        self,
        name: str,
        error: BaseException,
        placement: Placement,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.name = name
        self.placement = placement
        self.error = error
        label = QLabel(f"{name} could not be built:\n{error}")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setWordWrap(True)
        button = QPushButton("Show traceback")
        button.clicked.connect(self.show_traceback)
        layout = QVBoxLayout(self)
        layout.addStretch()
        layout.addWidget(label)
        layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()

    def show_traceback(self) -> None:
        show_failures(self, f"{self.name} could not be built", {self.name: self.error})


class FailuresButton(QPushButton):
    """A status bar button counting the components that failed, listing them on click."""

    def __init__(
        self, failures: Mapping[str, BaseException], parent: QWidget | None = None
    ) -> None:
        count = len(failures)
        super().__init__(f"{count} component{'s' if count > 1 else ''} failed", parent)
        self.failures = dict(failures)
        self.clicked.connect(self.list_failures)

    def list_failures(self) -> None:
        show_failures(self.window(), "Components that failed", self.failures)
