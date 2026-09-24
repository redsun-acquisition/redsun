"""A session attached to a service outside the process, and the service going away.

Runs against the IOC in ``tests/compose/compose.yaml``, and is skipped unless
``REDSUN_COMPOSE`` is set.
"""

from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import pytest
from ophyd_async.core import SignalRW
from ophyd_async.epics.core import EpicsDevice, PvSuffix
from psygnal import Signal
from qtpy.QtWidgets import QPushButton, QWidget

from redsun import (
    AsDevice,
    AsPresenter,
    AsService,
    AsView,
    Attach,
    Declare,
    DeviceMapping,
    Placement,
    Session,
    slot,
)
from redsun.aio import run_coro
from redsun.qt import Central, QtSession

if TYPE_CHECKING:
    from qtpy.QtWidgets import QApplication

    from .conftest import BuildSession

pytestmark = pytest.mark.compose

COMPOSE_FILE = Path(__file__).parent / "compose" / "compose.yaml"


class SimpleIoc(EpicsDevice):
    a: Annotated[SignalRW[int], PvSuffix("A")]


class SignalReader:
    """Reads one signal of every device when asked, and once more as it shuts down."""

    sig_read = Signal(str, object)

    def __init__(self, name: str, *, devices: DeviceMapping, signal: str) -> None:
        self.name = name
        self.devices = devices
        self.signal = signal
        self.read_at_shutdown: dict[str, object] = {}

    def read_all(self) -> dict[str, object]:
        return {
            name: run_coro(getattr(device, self.signal).get_value())
            for name, device in self.devices.items()
        }

    @slot
    def read(self) -> None:
        for name, value in self.read_all().items():
            self.sig_read.emit(name, value)

    def shutdown(self) -> None:
        self.read_at_shutdown = self.read_all()


class ReadingView(QWidget):
    """Asks for a reading with a button, and keeps every reading it is shown."""

    placement: Placement = Central()
    sig_read_requested = Signal()

    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.name = name
        self.readings: list[tuple[str, object]] = []
        self.read_button = QPushButton("read", self)
        self.read_button.clicked.connect(lambda: self.sig_read_requested.emit())

    @slot
    def show_reading(self, device: str, value: object) -> None:
        self.readings.append((device, value))


class Attached(Session):
    ioc: Annotated[AsService, Attach("REDSUN:ATTACHED:")]
    simple: Annotated[AsDevice[SimpleIoc], Declare(service="ioc")]


class AttachedPanel(QtSession):
    ioc: Annotated[AsService, Attach("REDSUN:ATTACHED:")]
    simple: Annotated[AsDevice[SimpleIoc], Declare(service="ioc")]
    reader: Annotated[AsPresenter[SignalReader], Declare(signal="a")]
    panel: AsView[ReadingView]

    def wire(self) -> None:
        self.connect(self.panel.sig_read_requested, self.reader.read)
        self.connect(self.reader.sig_read, self.panel.show_reading)


@pytest.fixture
def attachable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Find the IOC only through the port compose publishes on the loopback."""
    monkeypatch.setenv("EPICS_CA_ADDR_LIST", "127.0.0.1")
    monkeypatch.setenv("EPICS_CA_AUTO_ADDR_LIST", "NO")


def compose(*command: str) -> None:
    subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), *command],
        check=True,
        capture_output=True,
    )


def read(device: SimpleIoc) -> int:
    value: int = run_coro(device.a.get_value())
    return value


def test_an_attached_service_that_stops_times_out_and_answers_once_back(
    attachable: None, build: BuildSession
) -> None:
    """Channels recover on their own: no reconnect is asked for."""
    app = build(Attached)
    before = read(app.simple)

    compose("stop", "ioc")
    try:
        with pytest.raises(TimeoutError):
            read(app.simple)
    finally:
        compose("start", "ioc")

    # the IOC is another process, with nothing to wait on but its answer
    deadline = time.monotonic() + 120
    while True:
        try:
            after = read(app.simple)
            break
        except TimeoutError:
            if time.monotonic() > deadline:
                raise

    assert after == before


@pytest.mark.qt
def test_a_session_attached_to_an_ioc_shuts_down_cleanly(
    attachable: None,
    qapp: QApplication,
    build: BuildSession,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A view reads the IOC through a presenter, and shutdown ends each in turn.

    The presenter still reads the IOC as it shuts down, and the view is
    destroyed, without a warning.
    """
    app = build(AttachedPanel)
    panel, reader = app.panel, app.reader

    panel.read_button.click()
    caplog.clear()
    app.shutdown()

    with pytest.raises(RuntimeError, match="deleted"):
        panel.isVisible()
    assert [
        r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING
    ] == []
    assert panel.readings == [("simple", 1)]
    assert reader.read_at_shutdown == {"simple": 1}
