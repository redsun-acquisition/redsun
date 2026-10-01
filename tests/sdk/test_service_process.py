"""A service process learns its identity, signals readiness and stops through `redsun.services`."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from redsun.services import Service, identity, ready, wait_for_stop
from redsun.services._process import NAME_VARIABLE, READY_VARIABLE
from redsun.services._transports import (
    CHANNEL_ACCESS,
    PV_ACCESS,
    TRANSPORTS,
    ChannelAccess,
    PVAccess,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

PROCESS_STAND_IN = "mock_pkg.service.process_stand_in"
PROCESS_READY = "process stand-in ready"
REACHABLE_STAND_IN = "mock_pkg.service.reachable_stand_in"
REACHABLE_READY = "reachable stand-in ready"
MOCK_PACKAGES = str(Path(__file__).parents[1] / "launchable")


@pytest.fixture
def launch(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., Service]]:
    """Make process stand-ins, restoring the CA address list and stopping them after."""
    monkeypatch.setenv("PYTHONPATH", MOCK_PACKAGES)
    monkeypatch.setenv("EPICS_CA_ADDR_LIST", "")
    monkeypatch.setitem(TRANSPORTS, CHANNEL_ACCESS, ChannelAccess())
    made: list[Service] = []

    def make(*options: str, ready: str | None = PROCESS_READY) -> Service:
        made.append(
            Service(
                "camera",
                prefix="SIM:",
                module=PROCESS_STAND_IN,
                args=options,
                ready=ready,
                stop_timeout=5,
            )
        )
        return made[-1]

    yield make
    for launched in made:
        launched.stop()


@pytest.fixture
def service_log(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    """Capture everything the `redsun` logger tree records, services included."""
    caplog.set_level(logging.DEBUG, logger="redsun")
    return caplog


def messages(caplog: pytest.LogCaptureFixture, level: int) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno == level]


@pytest.mark.parametrize("options", [(), ("--blocking",)])
def test_a_service_on_the_process_functions_starts_and_stops_when_asked(
    options: tuple[str, ...],
    launch: Callable[..., Service],
    service_log: pytest.LogCaptureFixture,
) -> None:
    """Start a service on its declared ready text and stop it cleanly, awaiting or blocking."""
    service = launch(*options)

    service.start()
    service.stop()

    output = messages(service_log, logging.DEBUG)
    assert "identity ServiceIdentity(name='camera', prefix='SIM:')" in output
    assert "asked to stop" in output
    assert "Service 'camera' stopped with exit code 0" in messages(
        service_log, logging.INFO
    )


def test_a_stale_ready_text_in_the_session_does_not_reach_a_service(
    launch: Callable[..., Service],
    service_log: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pass no ready text to a service declared without one, whatever the session holds."""
    monkeypatch.setenv(READY_VARIABLE, "stale ready text")
    service = launch(ready=None)

    service.start()
    service.stop()

    assert "stale ready text" not in messages(service_log, logging.DEBUG)


def test_ready_prints_nothing_without_a_declared_text(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Print nothing from `ready` when the declaration gives no ready text."""
    monkeypatch.delenv(READY_VARIABLE, raising=False)

    ready()

    assert capsys.readouterr().out == ""


async def test_a_service_run_alone_has_no_identity_and_keeps_waiting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Report no identity and keep waiting for a stop request when no session launched the process."""
    monkeypatch.delenv(NAME_VARIABLE, raising=False)

    assert identity() is None
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(wait_for_stop(), timeout=0.2)


@pytest.mark.parametrize(
    ("level", "debug"),
    [
        (
            logging.DEBUG,
            {
                ("redsun.service.camera.stand_in", "stdlib debug"),
                ("redsun.service.camera.__main__", "loguru debug"),
            },
        ),
        (logging.INFO, set()),
    ],
)
def test_a_service_logs_at_the_level_its_session_records_at(
    level: int,
    debug: set[tuple[str, str]],
    launch: Callable[..., Service],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Pass the session's level to a service, whose records keep their level and logger, once each."""
    caplog.set_level(level, logger="redsun")
    service = launch()

    service.start()
    service.stop()

    own = {"redsun.service.camera.stand_in", "redsun.service.camera.__main__"}
    records = [r for r in caplog.records if r.name in own]
    assert {
        (r.name, r.getMessage()) for r in records if r.levelno == logging.DEBUG
    } == debug
    info = [(r.name, r.getMessage()) for r in records if r.levelno == logging.INFO]
    assert (
        "redsun.service.camera.stand_in",
        f"level {logging.getLevelName(level)}",
    ) in info
    tree = [r for r in caplog.records if "from the redsun tree" in r.getMessage()]
    assert [(r.name, r.levelno) for r in tree] == [
        ("redsun.service.camera.redsun.stand_in", logging.INFO)
    ]


def test_a_pva_service_is_ready_once_its_pv_answers(
    monkeypatch: pytest.MonkeyPatch, service_log: pytest.LogCaptureFixture
) -> None:
    """Count a PVAccess service ready once its own PV answers on the loopback."""
    monkeypatch.setenv("PYTHONPATH", MOCK_PACKAGES)
    monkeypatch.setenv("EPICS_PVA_ADDR_LIST", "")
    monkeypatch.setitem(TRANSPORTS, PV_ACCESS, PVAccess())
    service = Service(
        "reachable",
        module=REACHABLE_STAND_IN,
        args=["--pv", "REACH:VALUE"],
        ready=REACHABLE_READY,
        stop_timeout=5,
        transport=PV_ACCESS,
    )

    try:
        service.start()
    finally:
        service.stop()

    info = messages(service_log, logging.INFO)
    assert "Service 'reachable' started" in info
    assert "Service 'reachable' stopped with exit code 0" in info
