"""A session attached to a service outside the process, and the service going away.

Runs against the IOC in ``tests/compose/compose.yaml``, and is skipped unless
``REDSUN_COMPOSE`` is set.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING, Annotated

import pytest
from helpers import component, shut_down_after_a_read
from mock_pkg.controller import SignalReader
from mock_pkg.view import ReadingView
from ophyd_async.core import SignalRW
from ophyd_async.epics.core import EpicsDevice, PvSuffix

from redsun.aio import run_coro
from redsun.containers import (
    AppContainer,
    declare_device,
    declare_presenter,
    declare_service,
    declare_view,
)
from redsun.qt import QtAppContainer

if TYPE_CHECKING:
    from qtpy.QtWidgets import QApplication

pytestmark = pytest.mark.compose

COMPOSE_FILE = Path(__file__).parents[1] / "compose" / "compose.yaml"


class SimpleIoc(EpicsDevice):
    a: Annotated[SignalRW[int], PvSuffix("A")]


class Attached(AppContainer):
    ioc = declare_service(prefix="REDSUN:ATTACHED:")
    simple = declare_device(SimpleIoc, service="ioc")


class AttachedPanel(QtAppContainer):
    ioc = declare_service(prefix="REDSUN:ATTACHED:")
    simple = declare_device(SimpleIoc, service="ioc")
    reader = declare_presenter(SignalReader, signal="a")
    panel = declare_view(ReadingView)

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
    attachable: None, containers: list[AppContainer]
) -> None:
    """Channels recover on their own: no reconnect is asked for."""
    app = Attached().build()
    containers.append(app)
    simple = component(app.devices, "simple", SimpleIoc)
    before = read(simple)

    compose("stop", "ioc")
    try:
        with pytest.raises(TimeoutError):
            read(simple)
    finally:
        compose("start", "ioc")

    deadline = time.monotonic() + 120
    while True:
        try:
            after = read(simple)
            break
        except TimeoutError:
            if time.monotonic() > deadline:
                raise

    assert after == before


@pytest.mark.qt
def test_a_session_attached_to_an_ioc_shuts_down_cleanly(
    attachable: None,
    qapp: QApplication,
    containers: list[AppContainer],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A view reads the IOC through a presenter, and shutdown ends each in turn.

    The presenter still reads the IOC as it shuts down, and the view is destroyed,
    without a warning.
    """
    app = AttachedPanel()
    containers.append(app)
    app.build()

    readings, read_at_shutdown = shut_down_after_a_read(
        app, app.panel, app.reader, caplog
    )

    assert readings == [("simple", 1)]
    assert read_at_shutdown == {"simple": 1}
