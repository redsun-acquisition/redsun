"""A Qt view slot is delivered on the main thread without asking for it."""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

import pytest
from mock_pkg.controller import AsyncMotorController
from mock_pkg.view import MockMotorView
from psygnal.qt import start_emitting_from_queue

from redsun.containers import AppContainer, declare_presenter, declare_view

if TYPE_CHECKING:
    from collections.abc import Iterator

    from qtpy.QtWidgets import QApplication

pytestmark = pytest.mark.qt

TIMEOUT = 5.0


class _App(AppContainer):
    mover = declare_presenter(AsyncMotorController)
    widget = declare_view(MockMotorView)

    def wire(self) -> None:
        # no thread= here: the affinity has to come from QtView
        self.connect(self.mover.sig_motor_moved, self.widget.note_position)


@pytest.fixture
def app(qapp: QApplication) -> Iterator[_App]:
    built = _App().build()
    yield built
    if built.is_built:
        built.shutdown()


def test_qt_view_slots_default_to_the_main_thread(app: _App) -> None:
    """The recorded link carries the affinity the base class declares."""
    (link,) = app.virtual_container.connections

    assert link.thread == "main"


def test_emission_from_a_worker_is_delivered_on_the_main_thread(
    app: _App, qapp: QApplication
) -> None:
    """The queued emission runs where Qt widgets can be touched."""
    start_emitting_from_queue()
    main = threading.get_ident()

    worker = threading.Thread(
        target=lambda: app.mover.sig_motor_moved.emit("my_motor", 1.0)
    )
    worker.start()
    worker.join()

    deadline = time.perf_counter() + TIMEOUT
    while not app.widget.positions and time.perf_counter() < deadline:
        qapp.processEvents()
        time.sleep(0.005)

    assert app.widget.positions == [("my_motor", 1.0)]
    assert app.widget.threads == [main]


def test_an_explicit_thread_overrides_the_class(qapp: QApplication) -> None:
    """The connection has the last word over the base class affinity."""

    class _Override(AppContainer):
        mover = declare_presenter(AsyncMotorController)
        widget = declare_view(MockMotorView)

        def wire(self) -> None:
            self.connect(
                self.mover.sig_motor_moved,
                self.widget.note_position,
                thread="current",
            )

    app = _Override().build()
    try:
        (link,) = app.virtual_container.connections
        assert link.thread == "current"
    finally:
        app.shutdown()
