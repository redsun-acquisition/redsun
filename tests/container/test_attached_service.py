"""A device attached to a service outside the process survives the service going away.

Runs against the IOC in ``tests/compose/compose.yaml``, and is skipped unless
``REDSUN_COMPOSE`` is set.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Annotated

import pytest
from ophyd_async.core import SignalRW
from ophyd_async.epics.core import EpicsDevice, PvSuffix

from redsun.aio import run_coro
from redsun.containers import AppContainer, declare_device, declare_service

pytestmark = pytest.mark.compose

COMPOSE_FILE = Path(__file__).parents[1] / "compose" / "compose.yaml"


class SimpleIoc(EpicsDevice):
    a: Annotated[SignalRW[int], PvSuffix("A")]


class Attached(AppContainer):
    ioc = declare_service(prefix="REDSUN:ATTACHED:")
    simple = declare_device(SimpleIoc, service="ioc")


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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Channels recover on their own: no reconnect is asked for."""
    monkeypatch.setenv("EPICS_CA_ADDR_LIST", "127.0.0.1")
    monkeypatch.setenv("EPICS_CA_AUTO_ADDR_LIST", "NO")
    app = Attached().build()
    simple = app.devices["simple"]
    assert isinstance(simple, SimpleIoc)
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
    app.shutdown()

    assert after == before
