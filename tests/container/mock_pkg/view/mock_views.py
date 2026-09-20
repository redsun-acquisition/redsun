from __future__ import annotations

import threading
from typing import Any, cast

from psygnal import Signal
from qtpy.QtWidgets import QApplication, QPushButton

from redsun.view import ViewPosition
from redsun.view.qt import QtView
from redsun.virtual import VirtualContainer, slot


class NotAView:
    """Listed under ``views`` in the manifest, but shaped like a presenter."""

    def __init__(self, name: str, devices: dict[str, Any], /) -> None:
        self.name = name
        self.devices = devices


class MockQtView(QtView):
    """Mock Qt view for testing."""

    def __init__(self, name: str, /, *, label: str = "", **kwargs: Any) -> None:
        super().__init__(name, **kwargs)
        self.label = label

    @property
    def view_position(self) -> ViewPosition:
        return ViewPosition.CENTER


class MockMotorView(QtView):
    """Mock Qt view requesting motor moves through the virtual container."""

    sig_motor_move = Signal(str, float)

    def __init__(self, name: str, /, *, motor: str = "my_motor", **kwargs: Any) -> None:
        super().__init__(name, **kwargs)
        self.motor = motor
        self.position = 42.0
        self.threads: list[int] = []
        self.positions: list[tuple[str, float]] = []
        self.move_button = QPushButton("move", self)
        self.move_button.clicked.connect(self._on_move_clicked)

    @property
    def view_position(self) -> ViewPosition:
        return ViewPosition.CENTER

    def register_providers(self, container: VirtualContainer) -> None:
        container.register_signals(self)

    @slot
    def note_position(self, motor: str, position: float) -> None:
        """Record the thread it ran on, to prove where delivery happened."""
        self.threads.append(threading.get_ident())
        self.positions.append((motor, position))

    def _on_move_clicked(self) -> None:
        self.sig_motor_move.emit(self.motor, self.position)


class ReadingView(QtView):
    """Asks for a reading with a button, and keeps every reading it is shown."""

    sig_read_requested = Signal()

    def __init__(self, name: str, /, **kwargs: Any) -> None:
        super().__init__(name, **kwargs)
        self.readings: list[tuple[str, object]] = []
        self.read_button = QPushButton("read", self)
        self.read_button.clicked.connect(lambda: self.sig_read_requested.emit())

    @property
    def view_position(self) -> ViewPosition:
        return ViewPosition.CENTER

    @slot
    def show_reading(self, device: str, value: object) -> None:
        self.readings.append((device, value))


class StyleRecordingView(QtView):
    """Records the application stylesheet in force when it is constructed.

    A hook that styles the application has to run before any view exists;
    asserting on a call list alone cannot tell that apart from running after.
    """

    def __init__(self, name: str, /, **kwargs: Any) -> None:
        super().__init__(name, **kwargs)
        app = QApplication.instance()
        self.stylesheet_at_build = (
            cast("QApplication", app).styleSheet() if app is not None else ""
        )

    @property
    def view_position(self) -> ViewPosition:
        return ViewPosition.CENTER


class BrokenView(QtView):
    """Refuses construction, so that a build has a view it cannot make."""

    def __init__(self, name: str, /, **kwargs: Any) -> None:
        raise RuntimeError("Broken view")

    @property
    def view_position(self) -> ViewPosition:
        return ViewPosition.CENTER

    @slot
    def note_position(self, motor: str, position: float) -> None: ...
