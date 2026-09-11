"""A queued emission left over at shutdown reaches live widgets, or nothing."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

import pytest
from mock_pkg.controller import AsyncMotorController
from mock_pkg.view import MockMotorView
from psygnal import emit_queued
from psygnal.qt import start_emitting_from_queue

from redsun.containers import declare_presenter, declare_view
from redsun.qt import QtAppContainer
from redsun.virtual import slot

if TYPE_CHECKING:
    from qtpy.QtWidgets import QApplication

pytestmark = pytest.mark.qt


class _ButtonWritingView(MockMotorView):
    """Writes each reading into a child widget, as a real view does."""

    def __init__(self, name: str, /, **kwargs: Any) -> None:
        super().__init__(name, **kwargs)
        self.texts: list[str] = []

    @slot
    def note_position(self, motor: str, position: float) -> None:
        """Record the reading, in the child widget as well as in Python."""
        self.move_button.setText(f"{motor} {position}")
        self.texts.append(self.move_button.text())
        super().note_position(motor, position)


class _App(QtAppContainer):
    mover = declare_presenter(AsyncMotorController)
    widget = declare_view(_ButtonWritingView)

    def wire(self) -> None:
        self.connect(self.mover.sig_motor_moved, self.widget.note_position)


def test_a_queued_emission_is_delivered_before_the_widgets_are_destroyed(
    qapp: QApplication,
) -> None:
    """A leftover reading is delivered while its widget can still take it."""
    # `build` is annotated as returning the base class, so the container is
    # kept under its own name for the declared members to resolve
    app = _App()
    app.build()
    widget = app.widget
    start_emitting_from_queue()

    # emitting from a worker parks the reading in the queue, and the event loop
    # is never spun afterwards, so it is still waiting at shutdown
    worker = threading.Thread(
        target=lambda: app.mover.sig_motor_moved.emit("my_motor", 1.0)
    )
    worker.start()
    worker.join()

    app.shutdown()

    assert widget.positions == [("my_motor", 1.0)]
    assert widget.texts == ["my_motor 1.0"]

    emit_queued()

    assert widget.positions == [("my_motor", 1.0)]
