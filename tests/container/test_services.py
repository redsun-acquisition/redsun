"""A container starts its services before its devices, and stops them on every path."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

import pytest
from mock_pkg.device import BrokenDevice, MyMotor
from mock_pkg.service.stand_in import READY
from ophyd_async.core import Device, SignalRW
from ophyd_async.epics.core import EpicsDevice, PvSuffix

from redsun.aio import run_coro
from redsun.containers import (
    AppContainer,
    declare_device,
    declare_presenter,
    declare_service,
)
from redsun.containers import container as container_module
from redsun.log import SessionFileHandler, session_log
from redsun.presenter import Presenter
from redsun.services import _service

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

STAND_IN = "mock_pkg.service.stand_in"


class PrefixedDevice(Device):
    def __init__(self, prefix: str, name: str = "") -> None:
        self.prefix = prefix
        super().__init__(name=name)


class DeviceWithServiceKeyword(Device):
    def __init__(self, name: str = "", service: str = "") -> None:
        super().__init__(name=name)


class Camera(EpicsDevice):
    exposure: Annotated[SignalRW[float], PvSuffix("Exposure")]


class ExposureReader(Presenter):
    """Reads every camera's exposure while it is built, as a presenter may."""

    def __init__(
        self, name: str, devices: Mapping[str, Device], /, **kwargs: Any
    ) -> None:
        super().__init__(name, devices)
        self.exposures = {
            device_name: run_coro(device.exposure.get_value())
            for device_name, device in devices.items()
            if isinstance(device, Camera)
        }


class TwoCameras(AppContainer):
    ioc_a = declare_service(
        module="mock_pkg.service.camera_ioc",
        ready="Server startup complete",
        prefix="A:",
        args=["--prefix", "A:"],
    )
    ioc_b = declare_service(
        module="mock_pkg.service.camera_ioc",
        ready="Server startup complete",
        prefix="B:",
        args=["--prefix", "B:"],
    )
    cam_a = declare_device(Camera, service="ioc_a")
    cam_b = declare_device(Camera, service="ioc_b")
    reader = declare_presenter(ExposureReader)


@pytest.fixture
def launchable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Let a launched service import ``mock_pkg``, and restore the CA address list."""
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).parent))
    monkeypatch.setenv("EPICS_CA_ADDR_LIST", "")
    monkeypatch.setattr(_service, "ports", {})


@pytest.fixture
def containers(launchable: None) -> Iterator[list[AppContainer]]:
    """Collect containers, shutting each down after the test whatever it did."""
    made: list[AppContainer] = []
    yield made
    for app in made:
        app.shutdown()


def open_log() -> SessionFileHandler:
    """Return the session log file's handler, held so it is readable after closing."""
    handler = session_log()
    assert handler is not None
    return handler


def logged(handler: SessionFileHandler) -> str:
    handler.flush()
    return "".join(path.read_text(encoding="utf-8") for path in handler.files)


def test_a_build_starts_services_first_and_shutdown_stops_them(
    containers: list[AppContainer], tmp_path: Path
) -> None:
    marker = tmp_path / "cleaned"

    class App(AppContainer):
        stand_in = declare_service(
            module=STAND_IN, ready=READY, args=["--marker", str(marker)]
        )

    app = App()
    containers.append(app)
    seen: list[str] = []
    app._report = seen.append

    app.build()
    assert app.services["stand_in"].running
    assert seen[0] == "services"
    app.shutdown()

    assert not app.stand_in.running
    assert marker.read_text() == "cleaned up"


def test_a_build_that_raises_stops_the_services_before_it_propagates(
    containers: list[AppContainer],
) -> None:
    class App(AppContainer):
        stand_in = declare_service(module=STAND_IN, ready=READY, stop_timeout=2)

        def wire(self) -> None:
            raise RuntimeError("wiring went wrong")

    app = App()
    containers.append(app)

    with pytest.raises(RuntimeError, match="wiring went wrong"):
        app.build()

    assert not app.stand_in.running
    assert "Service 'stand_in' stopped with exit code 0" in logged(open_log())


def test_shutdown_of_a_container_never_built_stops_its_started_services(
    containers: list[AppContainer],
) -> None:
    class App(AppContainer):
        stand_in = declare_service(module=STAND_IN, ready=READY)

    app = App()
    containers.append(app)
    app.start_services()
    assert app.services["stand_in"].running
    handler = open_log()

    app.shutdown()

    assert not app.stand_in.running
    assert "Service 'stand_in' stopped with exit code 0" in logged(handler)


def test_a_launched_service_logs_to_a_file_of_its_own(
    containers: list[AppContainer],
) -> None:
    warning = (
        '{"name": "ioc", "levelno": 30, "created": 1.0, "msg": "frame dropped", '
        '"exc_text": null}'
    )

    class App(AppContainer):
        stand_in = declare_service(
            module=STAND_IN, ready=READY, args=["--say", warning]
        )
        attached = declare_service(prefix="BL01:")

    app = App()
    containers.append(app)
    application = open_log()
    service = session_log("stand_in")
    assert service is not None
    assert session_log("attached") is None

    app.build()
    app.shutdown()

    assert "frame dropped" in logged(service)
    assert "frame dropped" not in logged(application)
    assert "Service 'stand_in' started" in logged(application)
    assert session_log("stand_in") is None


def test_a_device_naming_a_service_is_built_with_its_prefix() -> None:
    class App(AppContainer):
        beamline = declare_service(prefix="BL01:")
        stage = declare_device(PrefixedDevice, service="beamline")

    app = App().build()

    stage = app.devices["stage"]
    assert isinstance(stage, PrefixedDevice)
    assert stage.prefix == "BL01:"
    assert stage.name == "stage"


@pytest.mark.parametrize(
    ("cls", "kwargs", "reason"),
    [
        (PrefixedDevice, {"service": "beamline", "prefix": "X:"}, "and a prefix"),
        (DeviceWithServiceKeyword, {"service": "beamline"}, "'service' keyword"),
    ],
    ids=["service-and-prefix", "own-service-keyword"],
)
def test_a_device_declaration_naming_a_service_ambiguously_is_refused(
    cls: type[Device], kwargs: dict[str, str], reason: str
) -> None:
    with pytest.raises(TypeError, match=reason):

        class App(AppContainer):
            beamline = declare_service(prefix="BL01:")
            device = declare_device(cls, **kwargs)


def test_a_device_whose_service_did_not_start_is_skipped(
    containers: list[AppContainer], caplog: pytest.LogCaptureFixture
) -> None:
    class App(AppContainer):
        broken = declare_service(
            module=STAND_IN, ready=READY, args=["--no-ready", "--exit", "3"]
        )
        attached = declare_service(prefix="BL01:")
        camera = declare_device(PrefixedDevice, service="broken")
        stage = declare_device(PrefixedDevice, service="attached")
        typo = declare_device(PrefixedDevice, service="atached")

    app = App()
    containers.append(app)

    app.build()

    assert set(app.devices) == {"stage"}
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert (
        "Services started: 1/2\nNot started: broken (exited with code 3 before it "
        "was ready)"
    ) in warnings
    errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert "Failed to build device 'camera': service 'broken' was not started" in errors
    assert "Failed to build device 'typo': service 'atached' is not declared" in errors


def test_a_service_whose_every_device_failed_is_reported_unused(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class App(AppContainer):
        beamline = declare_service(prefix="BL01:")
        spare = declare_service(prefix="BL02:")
        broken = declare_device(BrokenDevice, service="beamline")
        motor = declare_device(MyMotor)

    App().build()

    (summary,) = [
        r.getMessage()
        for r in caplog.records
        if r.getMessage().startswith("Container built:")
    ]
    assert summary.endswith("Unused: beamline (no device built)")


def test_from_config_launches_a_plugin_service_and_attaches_to_the_rest(
    config_path: Path, mock_entry_points: None, containers: list[AppContainer]
) -> None:
    app = AppContainer.from_config(str(config_path / "mock_services_config.yaml"))
    containers.append(app)

    app.build()

    launched, beamline = app.services["launched"], app.services["beamline"]
    assert launched.running
    assert (launched.prefix, launched.stop_timeout) == ("SIM:", 2)
    assert not beamline.launched
    assert beamline.prefix == "BL01:"


def test_a_presenter_reads_two_caproto_iocs_while_it_is_built(
    containers: list[AppContainer], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The build connects the cameras first, and a rebuilt container reaches them again.

    Each IOC answers on a CA port of its own, which it keeps when it starts again,
    since libca reads the address list once per process. A channel left from the
    first build would take close to ten seconds to reconnect, past the timeout.
    """
    monkeypatch.setattr(container_module, "CONNECT_TIMEOUT", 3.0)
    for _ in range(2):
        app = TwoCameras()
        containers.append(app)

        app.build()

        reader = app.presenters["reader"]
        assert isinstance(reader, ExposureReader)
        assert reader.exposures == {"cam_a": 0.25, "cam_b": 0.25}
        app.shutdown()
