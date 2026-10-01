"""A launched service is started, drained, watched and stopped as a child process."""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from redsun import Launch
from redsun.log import GlobalFormatter
from redsun.services import Service, _service, _transports
from redsun.services._service import service_record
from redsun.services._transports import (
    CHANNEL_ACCESS,
    PV_ACCESS,
    TRANSPORTS,
    ChannelAccess,
    PVAccess,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from redsun.testing import StartService

STAND_IN = "mock_pkg.service.stand_in"
PVA_STAND_IN = "mock_pkg.service.pva_stand_in"
PVA_READY = "pva stand-in ready"
READY = "stand-in ready"
MOCK_PACKAGES = str(Path(__file__).parents[1] / "launchable")
STDLIB_WARNING = json.dumps(
    {
        "name": "caproto.ioc.camera",
        "levelno": logging.WARNING,
        "created": 1.5,
        "msg": "frame dropped at sequence 41",
        "exc_text": None,
    }
)
PVXS_WARNING = (
    "2026-09-21T14:54:02.293642200 WARN pvxs.tcp.setup Server unable to bind "
    "port 5075, falling back to 127.0.0.1:65003"
)
PVXS_CREATED = datetime(2026, 9, 21, 14, 54, 2, 293642).timestamp()
LOGURU_ERROR = json.dumps(
    {
        "text": "trigger failed\nTraceback (most recent call last):\nRuntimeError: no answer\n",
        "record": {
            "extra": {},
            "name": "fastcs_camera",
            "level": {"no": logging.ERROR, "name": "ERROR", "icon": "\u274c"},
            "message": "trigger failed",
            "time": {"timestamp": 2.5},
            "exception": {"type": "RuntimeError"},
        },
    }
)


class RecordingTransport(PVAccess):
    """PVAccess, recording whether it was released."""

    def __init__(self) -> None:
        self.released = False

    async def release(self) -> None:
        self.released = True


@pytest.fixture
def recording_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[RecordingTransport]:
    """Register a `recording` transport, and check it was released once the test ends.

    A test asks for it before `start_service`, so its teardown runs after the
    services were stopped.
    """
    transport = RecordingTransport()
    monkeypatch.setitem(TRANSPORTS, "recording", transport)
    yield transport
    assert transport.released


@pytest.fixture
def launch(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., Service]]:
    """Make stand-in services, restoring the CA address list and stopping them after."""
    monkeypatch.setenv("PYTHONPATH", MOCK_PACKAGES)
    monkeypatch.setenv("EPICS_CA_ADDR_LIST", "")
    monkeypatch.setitem(TRANSPORTS, CHANNEL_ACCESS, ChannelAccess())
    made: list[Service] = []

    def make(
        *options: str,
        stop_timeout: float = 0.5,
        name: str = "stand-in",
        prefix: str = "",
    ) -> Service:
        made.append(
            Service(
                name,
                prefix=prefix,
                module=STAND_IN,
                args=options,
                ready=READY,
                stop_timeout=stop_timeout,
            )
        )
        return made[-1]

    yield make
    for launched in made:
        launched.stop()


@pytest.fixture
def launch_pva(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., Service]]:
    """Make stand-in PVA services, restoring the address list and stopping them after."""
    monkeypatch.setenv("PYTHONPATH", MOCK_PACKAGES)
    monkeypatch.setenv("EPICS_PVA_ADDR_LIST", "")
    monkeypatch.setitem(TRANSPORTS, PV_ACCESS, PVAccess())
    made: list[Service] = []

    def make(name: str, pv: str, value: float) -> Service:
        made.append(
            Service(
                name,
                module=PVA_STAND_IN,
                args=("--pv", pv, "--value", str(value)),
                ready=PVA_READY,
                stop_timeout=0.5,
                transport=PV_ACCESS,
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


def logged_ports(caplog: pytest.LogCaptureFixture) -> list[str]:
    """Return the CA ports the stand-ins printed, in the order they printed them."""
    output = "\n".join(messages(caplog, logging.DEBUG))
    ports: list[str] = re.findall(r"^port (\d+)$", output, re.MULTILINE)
    return ports


def test_a_service_logs_its_output_and_cleans_up_when_stopped(
    launch: Callable[..., Service],
    service_log: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    """Log a service's output and let it clean up when stopped."""
    marker = tmp_path / "cleaned"
    stand_in = launch("--marker", str(marker))

    stand_in.start()
    was_running = stand_in.running
    stand_in.stop()

    assert (was_running, stand_in.running) == (True, False)
    assert marker.read_text() == "cleaned up"
    debug = messages(service_log, logging.DEBUG)
    assert READY in debug
    assert "cleaned up" in debug
    assert "Service 'stand-in' stopped with exit code 0" in messages(
        service_log, logging.INFO
    )


def test_a_service_not_ready_in_time_is_stopped_with_its_output_logged(
    launch: Callable[..., Service],
    service_log: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stop a service not ready in time and log its last output."""
    monkeypatch.setattr(_service, "STARTUP_TIMEOUT", 0.5)
    stand_in = launch("--no-ready")

    with pytest.raises(TimeoutError, match="not ready after 0.5 s"):
        stand_in.start()

    assert not stand_in.running
    (error,) = messages(service_log, logging.ERROR)
    assert error.startswith("Service 'stand-in' not ready after 0.5 s; last output:")
    assert "port " in error


def test_a_service_exiting_before_it_is_ready_is_reported_at_once(
    launch: Callable[..., Service],
    service_log: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Raise as soon as a service exits before it is ready, not at the timeout."""
    monkeypatch.setattr(_service, "STARTUP_TIMEOUT", 10.0)
    stand_in = launch("--no-ready", "--exit", "3")
    started = time.monotonic()

    with pytest.raises(RuntimeError, match="exited with code 3 before it was ready"):
        stand_in.start()

    assert time.monotonic() - started < 5
    assert not stand_in.running
    (error,) = messages(service_log, logging.ERROR)
    assert error.startswith(
        "Service 'stand-in' exited with code 3 before it was ready; last output:"
    )
    assert error.endswith("exiting on request")


@pytest.mark.parametrize(
    ("options", "cleans_up"),
    [
        # SIGINT is the second step on POSIX only; Windows goes straight to kill
        (("--ignore-stdin",), sys.platform != "win32"),
        (("--ignore-stdin", "--ignore-sigint"), False),
    ],
    ids=["ignores-stdin", "ignores-stdin-and-sigint"],
)
def test_a_service_ignoring_the_stop_request_is_stopped_by_the_next_step(
    launch: Callable[..., Service],
    service_log: pytest.LogCaptureFixture,
    tmp_path: Path,
    options: tuple[str, ...],
    cleans_up: bool,
) -> None:
    """Stop a service that ignores the stop request by the next, stronger step."""
    marker = tmp_path / "cleaned"
    stand_in = launch(*options, "--marker", str(marker))
    stand_in.start()

    stand_in.stop()

    assert not stand_in.running
    assert marker.exists() is cleans_up
    killed = any("killing it" in m for m in messages(service_log, logging.WARNING))
    assert killed is not cleans_up


def test_a_ready_service_exiting_unasked_emits_its_name_and_code(
    launch: Callable[..., Service], service_log: pytest.LogCaptureFixture
) -> None:
    """Emit the name and exit code of a ready service that exits unasked."""
    exits: list[tuple[str, int]] = []
    emitted = threading.Event()

    def record(name: str, code: int) -> None:
        exits.append((name, code))
        emitted.set()

    stand_in = launch("--exit", "7")
    stand_in.sig_exited.connect(record)
    stand_in.start()

    assert emitted.wait(5)
    assert exits == [("stand-in", 7)]
    (error,) = messages(service_log, logging.ERROR)
    assert error.startswith("Service 'stand-in' exited with code 7; last output:")


def test_a_stopped_service_emits_no_exit(launch: Callable[..., Service]) -> None:
    """Emit no exit for a service stopped on request."""
    exits: list[tuple[str, int]] = []
    stand_in = launch()
    stand_in.sig_exited.connect(lambda name, code: exits.append((name, code)))
    stand_in.start()

    stand_in.stop()

    assert exits == []


def test_a_port_another_service_holds_is_not_given_again(
    launch: Callable[..., Service],
    service_log: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Draw a new port when the one drawn is held by another service."""
    drawn = iter([40001, 40001, 40002])
    monkeypatch.setattr(_transports, "free_udp_port", lambda: next(drawn))
    first, second = launch(name="first"), launch(name="second")

    first.start()
    second.start()

    assert logged_ports(service_log) == ["40001", "40002"]


def test_each_launched_service_gets_a_ca_port_of_its_own_in_the_address_list(
    launch: Callable[..., Service], service_log: pytest.LogCaptureFixture
) -> None:
    """Give each service its own CA port and list them all in the address list."""
    first, second = launch(name="first"), launch(name="second")

    first.start()
    second.start()

    ports = logged_ports(service_log)
    assert len(set(ports)) == 2
    assert os.environ["EPICS_CA_ADDR_LIST"].split() == [
        f"127.0.0.1:{port}" for port in ports
    ]


def test_two_pva_services_answer_on_the_loopback(
    launch_pva: Callable[..., Service], service_log: pytest.LogCaptureFixture
) -> None:
    """Bind two PVA services to the loopback and list it in the address list."""
    p4p = pytest.importorskip("p4p.client.thread")

    first = launch_pva("first", "SIM:FIRST", 1.0)
    second = launch_pva("second", "SIM:SECOND", 2.0)
    first.start()
    second.start()

    assert os.environ["EPICS_PVA_ADDR_LIST"].split() == ["127.0.0.1"]
    assert messages(service_log, logging.DEBUG).count("interface 127.0.0.1") == 2
    assert "unable to bind" not in service_log.text
    with p4p.Context("pva") as client:
        assert float(client.get("SIM:FIRST", timeout=10.0)) == 1.0
        assert float(client.get("SIM:SECOND", timeout=10.0)) == 2.0


@pytest.mark.parametrize(
    ("transport", "variable", "before"),
    [
        (PVAccess(), "EPICS_PVA_ADDR_LIST", ""),
        (ChannelAccess(), "EPICS_CA_ADDR_LIST", ""),
        (PVAccess(), "EPICS_PVA_ADDR_LIST", "10.0.0.1"),
    ],
)
def test_a_transport_lists_its_address_again_once_the_list_is_cleared(
    monkeypatch: pytest.MonkeyPatch,
    transport: PVAccess | ChannelAccess,
    variable: str,
    before: str,
) -> None:
    """List the address once, again after a reset, and keep what the list held."""
    monkeypatch.setenv(variable, before)
    transport.publish("first")
    transport.publish("first")
    listed = os.environ[variable].split()
    monkeypatch.setenv(variable, before)
    transport.publish("first")

    assert os.environ[variable].split() == listed
    assert listed[: len(before.split())] == before.split()
    assert len(listed) == len(before.split()) + 1


@pytest.mark.parametrize("value", [1.0, 2.0])
def test_a_pva_service_started_in_each_test_answers(
    start_service: StartService,
    monkeypatch: pytest.MonkeyPatch,
    value: float,
) -> None:
    """Reach a PVA service started in each of two tests of one process."""
    p4p = pytest.importorskip("p4p.client.thread")
    monkeypatch.setenv("PYTHONPATH", MOCK_PACKAGES)

    start_service(
        "started",
        Launch(
            PVA_STAND_IN,
            args=("--pv", "SIM:STARTED", "--value", str(value)),
            ready=PVA_READY,
            stop_timeout=0.5,
        ),
        transport="pv-access",
    )

    with p4p.Context("pva") as client:
        assert float(client.get("SIM:STARTED", timeout=10.0)) == value


def test_a_started_service_releases_its_transport_once_it_stops(
    recording_transport: RecordingTransport,
    start_service: StartService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Release a started service's transport after the test, as a session does."""
    pytest.importorskip("p4p")
    monkeypatch.setenv("PYTHONPATH", MOCK_PACKAGES)

    start_service(
        "released",
        Launch(
            PVA_STAND_IN,
            args=("--pv", "SIM:RELEASED", "--value", "1.0"),
            ready=PVA_READY,
            stop_timeout=0.5,
        ),
        transport="recording",
    )

    assert not recording_transport.released


@pytest.mark.parametrize(
    ("line", "name", "level", "message", "created", "traceback"),
    [
        (
            "a plain print",
            "redsun.service.cam",
            logging.DEBUG,
            "a plain print",
            None,
            None,
        ),
        (
            STDLIB_WARNING,
            "redsun.service.cam.caproto.ioc.camera",
            logging.WARNING,
            "frame dropped at sequence 41",
            1.5,
            None,
        ),
        (
            LOGURU_ERROR,
            "redsun.service.cam.fastcs_camera",
            logging.ERROR,
            "trigger failed",
            2.5,
            "Traceback (most recent call last):\nRuntimeError: no answer",
        ),
        (
            PVXS_WARNING,
            "redsun.service.cam.pvxs.tcp.setup",
            logging.WARNING,
            "Server unable to bind port 5075, falling back to 127.0.0.1:65003",
            PVXS_CREATED,
            None,
        ),
        (
            '{"name": "incomplete"}',
            "redsun.service.cam",
            logging.DEBUG,
            '{"name": "incomplete"}',
            None,
            None,
        ),
        ("[1, 2]", "redsun.service.cam", logging.DEBUG, "[1, 2]", None, None),
    ],
    ids=[
        "plain",
        "stdlib-json",
        "loguru-json",
        "pvxs",
        "incomplete-json",
        "not-an-object",
    ],
)
def test_a_line_of_output_becomes_the_record_it_describes(
    line: str,
    name: str,
    level: int,
    message: str,
    created: float | None,
    traceback: str | None,
) -> None:
    """Turn a line of service output into the record it describes."""
    record = service_record("cam", line)

    assert (record.name, record.levelno, record.getMessage()) == (name, level, message)
    assert record.exc_text == traceback
    if created is not None:
        assert record.created == created


def test_a_rebuilt_record_names_its_service_and_no_location() -> None:
    """Format a service record with its service and logger names, no location."""
    text = GlobalFormatter(datefmt="%H").format(service_record("cam", STDLIB_WARNING))

    assert text.endswith(
        "[WARNING][cam -> caproto.ioc.camera]: frame dropped at sequence 41"
    )


def test_non_ascii_output_arrives_intact(
    launch: Callable[..., Service], service_log: pytest.LogCaptureFixture
) -> None:
    """Log non-ASCII service output unchanged."""
    message = "température 21 °C \u2713"
    line = json.dumps(
        {**json.loads(STDLIB_WARNING), "msg": message}, ensure_ascii=False
    )
    stand_in = launch("--say", line)

    # The stand-in prints this line before its readiness one, so `start` cannot
    # return until the drain has logged it.
    stand_in.start()

    assert message in messages(service_log, logging.WARNING)


def test_a_service_started_again_keeps_its_port(
    launch: Callable[..., Service], service_log: pytest.LogCaptureFixture
) -> None:
    """Keep the same port when a service is started again."""
    stand_in = launch()

    stand_in.start()
    stand_in.stop()
    stand_in.start()

    ports = logged_ports(service_log)
    assert len(ports) == 2
    assert len(set(ports)) == 1
    assert os.environ["EPICS_CA_ADDR_LIST"].split() == [f"127.0.0.1:{ports[0]}"]


def test_an_attached_service_has_nothing_to_start_or_stop() -> None:
    """Launch no process for a service with no module."""
    attached = Service("beamline", prefix="BL01:")

    attached.start()
    assert not attached.running
    attached.stop()

    assert not attached.launched


def test_arguments_without_a_module_are_refused() -> None:
    """Refuse arguments given without a module to run."""
    with pytest.raises(TypeError, match="no module to run"):
        Service("beamline", args=["--prefix", "BL01:"])


def test_a_service_ends_when_the_process_that_launched_it_dies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Clean up and exit a service once the process that launched it dies."""
    monkeypatch.setenv("PYTHONPATH", MOCK_PACKAGES)
    marker = tmp_path / "cleaned"
    parent = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import time; from redsun.services import Service; "
                f"Service('orphan', module={STAND_IN!r}, "
                f"args=['--marker', {str(marker)!r}], ready={READY!r}).start(); "
                "print('launched', flush=True); time.sleep(60)"
            ),
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert parent.stdout is not None
        # redsun's own log lines reach the same stdout first
        assert "launched" in (line.strip() for line in parent.stdout)
    finally:
        parent.kill()
        parent.wait()

    deadline = time.monotonic() + 10
    while not marker.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert marker.read_text() == "cleaned up"


def test_a_launched_service_reads_its_name_and_prefix_from_the_environment(
    launch: Callable[..., Service],
    service_log: pytest.LogCaptureFixture,
) -> None:
    """Pass a launched service its name and prefix through the environment."""
    stand_in = launch(name="camera", prefix="SIM:")

    stand_in.start()
    stand_in.stop()

    assert "service camera prefix SIM:" in messages(service_log, logging.DEBUG)


def test_a_service_given_an_unknown_transport_names_the_known_ones() -> None:
    """Refuse an unknown transport, naming the ones a session accepts."""
    with pytest.raises(ValueError, match="'channel-access', 'pv-access'"):
        Service("misnamed", module=STAND_IN, transport="pv_access")


@pytest.mark.parametrize(
    ("args", "expected"),
    [
        ({"adapter": "DahengGalaxy"}, ["--adapter", "DahengGalaxy"]),
        ({"exposure": 0.5, "binning": 2}, ["--exposure", "0.5", "--binning", "2"]),
        ({"count": 0}, ["--count", "0"]),
        ({"verbose": True}, ["--verbose"]),
        ({"verbose": False, "port": None}, []),
        ({"axes": ["x", "y"]}, ["--axes", "x", "y"]),
        (["--adapter", "DahengGalaxy"], ["--adapter", "DahengGalaxy"]),
    ],
)
def test_arguments_are_given_as_a_list_or_as_options(
    args: list[str] | dict[str, Any], expected: list[str]
) -> None:
    """Turn a mapping of options into command-line arguments, and keep a list as given."""
    assert Service("camera", module="mylab.camera", args=args).args == expected


def test_arguments_given_as_text_are_refused() -> None:
    """Refuse arguments written as one piece of text."""
    with pytest.raises(TypeError, match="a list or a mapping"):
        Service("camera", module="mylab.camera", args="--port COM4")
