from __future__ import annotations

from typing import Any

from psygnal import Signal
from qtpy.QtWidgets import QPushButton

from redsun.view import ViewPosition
from redsun.view.qt import QtView
from redsun.virtual import VirtualContainer


class MockQtView(QtView):
    """Mock Qt view for testing."""

    def __init__(self, name: str, /, **kwargs: Any) -> None:
        super().__init__(name, **kwargs)

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
        self.move_button = QPushButton("move", self)
        self.move_button.clicked.connect(self._on_move_clicked)

    @property
    def view_position(self) -> ViewPosition:
        return ViewPosition.CENTER

    def register_providers(self, container: VirtualContainer) -> None:
        container.register_signals(self)

    def _on_move_clicked(self) -> None:
        self.sig_motor_move.emit(self.motor, self.position)
