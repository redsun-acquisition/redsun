"""Run a session so the colour-scheme control and the teardown can be watched.

Not collected by pytest, which reads ``tests`` only, and it wants a real
display: the offscreen platform ignores ``setColorScheme`` and never repaints.

```
uv run python demo_session.py          # starts in the platform's scheme
uv run python demo_session.py dark     # starts dark
```

The control at the right of the toolbar cycles system, light and dark. Closing
the window ends the session, and every step of the teardown prints as it runs,
in the order it runs:

```
layout    saved to ...    first, while the window still exists
shutdown  'hardware'      each component's own teardown, in reverse build order
shutdown  'acquisition'
close     'hardware'      then each widget's closeEvent, before it is deleted
close     'acquisition'
```

The window and the views are destroyed after that, then the application, then
the async backend. Run it twice: the second run comes up with the docks where
the first left them, read back from that file.
"""

from __future__ import annotations

import sys
from typing import Any

from qtpy.QtCore import Qt  # noqa: TC002
from qtpy.QtGui import QGuiApplication
from qtpy.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from redsun.experimental import AsView, Placement  # noqa: TC001
from redsun.experimental.containers.qt import Central, Dock, QtAppContainer


def report(step: str, detail: str) -> None:
    """Print one line of the teardown, so the order is visible."""
    print(f"{step:9} {detail}", flush=True)


class Watched(QWidget):
    """A view that says when it is shut down and when its widget closes."""

    def __init__(self, name: str, /) -> None:
        super().__init__()
        self.name = name

    def shutdown(self) -> None:
        """Report the component's own teardown, which runs first."""
        report("shutdown", repr(self.name))

    def closeEvent(self, event: Any) -> None:
        """Report the widget's close, which only an explicit close delivers."""
        report("close", repr(self.name))
        super().closeEvent(event)


class Acquisition(Watched):
    """The central view, with enough widgets that a repaint is obvious."""

    placement: Placement = Central()

    def __init__(self, name: str, /) -> None:
        """Fill the central area, and report the scheme Qt says is in force."""
        super().__init__(name)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.addRow("Exposure (ms)", QLineEdit("50"))
        channels = QComboBox()
        channels.addItems(["Brightfield", "GFP", "mCherry"])
        form.addRow("Channel", channels)
        form.addRow(QCheckBox("Autofocus"))
        layout.addLayout(form)

        progress = QProgressBar()
        progress.setValue(42)
        layout.addWidget(progress)
        layout.addWidget(QPushButton("Acquire"))
        layout.addStretch()

        self._reported = QLabel()
        layout.addWidget(self._reported)

        hints = QGuiApplication.styleHints()
        if hints is not None:
            hints.colorSchemeChanged.connect(self._show_scheme)
            self._show_scheme(hints.colorScheme())

    def _show_scheme(self, scheme: Qt.ColorScheme) -> None:
        self._reported.setText(f"Qt reports: {scheme.name}")


class Hardware(Watched):
    """A docked view, so a dock area is there to be moved and remembered."""

    placement: Placement = Dock("left")

    def __init__(self, name: str, /) -> None:
        """Fill the left dock with something to look at."""
        super().__init__(name)
        layout = QVBoxLayout(self)
        for label in ("Stage", "Camera", "Shutter"):
            layout.addWidget(QLabel(label))
        layout.addStretch()


class Demo(QtAppContainer):
    """A session carrying the colour-scheme control every Qt session has."""

    __slots__ = ()

    acquisition: AsView[Acquisition]
    hardware: AsView[Hardware]

    def save_layout(self) -> None:
        """Save as usual, and say where it went."""
        super().save_layout()
        report("layout", f"saved to {self.settings.path}")


if __name__ == "__main__":
    config: dict[str, Any] = {"name": "demo-session"}
    if len(sys.argv) > 1:
        config["color_scheme"] = sys.argv[1]
    Demo(config).run()
