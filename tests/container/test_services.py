"""A container starts its services before its devices, and stops them on every path."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any

import pytest
from helpers import component, shut_down_after_a_read
from mock_pkg.controller import SignalReader
from mock_pkg.device import BrokenDevice, MyMotor
from mock_pkg.service.stand_in import READY
from mock_pkg.view import ReadingView
from ophyd_async.core import Device, SignalRW
from ophyd_async.epics.core import EpicsDevice, PvSuffix

from redsun.aio import run_coro
from redsun.containers import (
    AppContainer,
    declare_device,
    declare_presenter,
    declare_service,
    declare_view,
)
from redsun.containers import container as container_module
from redsun.log import SessionFileHandler, session_log
from redsun.presenter import Presenter
from redsun.qt import QtAppContainer
from redsun.services._transports import PV_ACCESS

if TYPE_CHECKING:
    from collections.abc import Mapping

    from qtpy.QtWidgets import QApplication

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


class CameraPanel(QtAppContainer):
    ioc_a = declare_service(
        module="mock_pkg.service.camera_ioc",
        ready="Server startup complete",
        prefix="A:",
        args=["--prefix", "A:"],
    )
    cam_a = declare_device(Camera, service="ioc_a")
    reader = declare_presenter(SignalReader, signal="exposure")
    panel = declare_view(ReadingView)

    def wire(self) -> None:
        self.connect(self.panel.sig_read_requested, self.reader.read)
        self.connect(self.reader.sig_read, self.panel.show_reading)


@pytest.fixture(autouse=True)
def launchable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Let a launched service import ``mock_pkg``, and restore the CA address list.

    The transport's port map is left alone: libca reads the address list once per
    process, so a service keeps the port it first got from test to test.
    """
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).parent))
    monkeypatch.setenv("EPICS_CA_ADDR_LIST", "")


def session_file(path: Path, services: str) -> Path:
    """Write a session file at *path* whose ``services`` section is *services*."""
    path.write_text(
        "schema_version: 1.0\nfrontend: pyqt\nsession: transports\n"
        f"services:\n{services}",
        encoding="utf-8",
    )
    return path


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

    app.build()
    assert app.services["stand_in"].running
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


def test_services_start_once_until_shutdown(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class App(AppContainer):
        beamline = declare_service(prefix="BL01:")

    app = App()
    app.start_services()
    app.build()
    app.shutdown()
    app.start_services()
    app.shutdown()

    started = [r for r in caplog.records if r.getMessage() == "Services started: 1/1"]
    assert len(started) == 2


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


def test_an_aliased_service_is_named_by_its_alias() -> None:
    class App(AppContainer):
        ioc = declare_service(prefix="BL01:", alias="beamline")
        stage = declare_device(PrefixedDevice, service="beamline")

    app = App().build()

    assert app.ioc is app.services["beamline"]
    stage = app.devices["stage"]
    assert isinstance(stage, PrefixedDevice)
    assert stage.prefix == "BL01:"


def test_a_service_it_cannot_make_is_refused_as_the_class_is_created() -> None:
    with pytest.raises(TypeError, match="'ioc' gives args but no module"):

        class App(AppContainer):
            ioc = declare_service(args=["--prefix", "X:"])


def test_a_session_file_service_it_cannot_make_is_refused(tmp_path: Path) -> None:
    config = tmp_path / "session.yaml"
    config.write_text(
        "schema_version: 1.0\nfrontend: pyqt\nsession: refused\n"
        "services:\n  ioc:\n    launch: attach\n",
        encoding="utf-8",
    )

    with pytest.raises(TypeError, match="launch"):
        AppContainer.from_config(str(config))


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
    assert not any("Unused:" in message for message in warnings)


def test_a_device_naming_a_service_without_a_prefix_is_skipped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class App(AppContainer):
        beamline = declare_service()
        stage = declare_device(PrefixedDevice, service="beamline")

    app = App().build()

    assert set(app.devices) == set()
    errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert (
        "Failed to build device 'stage': service 'beamline' gives no prefix" in errors
    )


def test_a_service_whose_every_device_failed_is_reported_unused(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class App(AppContainer):
        beamline = declare_service(prefix="BL01:")
        spare = declare_service(prefix="BL02:")
        stages = declare_service(prefix="ST:")
        broken = declare_device(BrokenDevice, service="beamline")
        broken_stage = declare_device(BrokenDevice, service="stages")
        stage = declare_device(PrefixedDevice, service="stages")
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


def test_a_service_its_plugin_does_not_list_is_left_out_with_one_error(
    mock_entry_points: None,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    config = tmp_path / "session.yaml"
    config.write_text(
        "schema_version: 1.0\nfrontend: pyqt\nsession: left-out\n"
        "services:\n  ioc:\n    plugin_name: mock-pkg\n    plugin_id: missing\n",
        encoding="utf-8",
    )

    app = AppContainer.from_config(str(config))

    assert "ioc" not in app.services
    errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert errors == ['Plugin "mock-pkg" does not contain the id "missing".']


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


@pytest.mark.qt
def test_a_session_with_one_of_each_component_shuts_down_cleanly(
    containers: list[AppContainer],
    qapp: QApplication,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A view reads a launched IOC through a presenter, and shutdown ends each in turn.

    The presenter still reads the camera as it shuts down, the view is destroyed,
    and the IOC exits once its input closes, all without a warning. The service is
    named as in ``TwoCameras``, so its IOC answers on a port libca already lists
    when the process first used Channel Access in that test.
    """
    app = CameraPanel()
    containers.append(app)
    app.build()

    readings, read_at_shutdown = shut_down_after_a_read(
        app, app.panel, app.reader, caplog
    )

    assert readings == [("cam_a", 0.25)]
    assert read_at_shutdown == {"cam_a": 0.25}
    assert not app.ioc_a.running
    messages = [r.getMessage() for r in caplog.records]
    assert "Service 'ioc_a' stopped with exit code 0" in messages


def test_a_session_file_names_what_its_services_speak(tmp_path: Path) -> None:
    config = session_file(
        tmp_path / "session.yaml",
        "  transport: pv-access\n  beamline:\n    prefix: 'BL01:'\n",
    )

    app = AppContainer.from_config(str(config))

    assert app.transport == PV_ACCESS
    assert app.services["beamline"].transport == PV_ACCESS


def test_a_transport_redsun_does_not_have_is_refused_in_a_session_file(
    tmp_path: Path,
) -> None:
    config = session_file(tmp_path / "session.yaml", "  transport: carrier-pigeon\n")

    with pytest.raises(TypeError, match="carrier-pigeon"):
        AppContainer.from_config(str(config))


def test_a_transport_redsun_does_not_have_is_refused_on_the_class() -> None:
    with pytest.raises(TypeError, match="carrier-pigeon"):

        class App(AppContainer):
            transport = "carrier-pigeon"


def test_layered_files_must_agree_on_the_transport(tmp_path: Path) -> None:
    under = session_file(tmp_path / "under.yaml", "  transport: channel-access\n")
    over = session_file(tmp_path / "over.yaml", "  transport: pv-access\n")

    with pytest.raises(ValueError, match="contradicts"):

        class App(AppContainer, config=[under, over]):
            pass


def test_a_component_named_transport_is_refused() -> None:
    with pytest.raises(TypeError, match="names a component 'transport'"):

        class App(AppContainer):
            transport = declare_service(prefix="BL01:")  # type: ignore[assignment]


def test_a_session_file_declares_a_service_for_a_container_class(
    tmp_path: Path,
) -> None:
    """A class taking a session file gets the services that file declares.

    The same file works through `from_config`, so a session written once must
    not need its services repeated in the class body to reach a device.
    """
    config = tmp_path / "session.yaml"
    config.write_text(
        "schema_version: 1.0\nfrontend: pyqt\nsession: from-a-file\n"
        'services:\n  beamline:\n    prefix: "BL01:"\n',
        encoding="utf-8",
    )

    class App(AppContainer, config=config):
        stage = declare_device(PrefixedDevice, service="beamline")

    app = App().build()

    assert set(app.services) == {"beamline"}
    stage = app.devices["stage"]
    assert isinstance(stage, PrefixedDevice)
    assert stage.prefix == "BL01:"


def test_a_class_body_service_wins_over_the_session_file(tmp_path: Path) -> None:
    """The class body is the later word on a service the file also declares."""
    config = tmp_path / "session.yaml"
    config.write_text(
        "schema_version: 1.0\nfrontend: pyqt\nsession: overridden\n"
        'services:\n  beamline:\n    prefix: "FILE:"\n',
        encoding="utf-8",
    )

    class App(AppContainer, config=config):
        beamline = declare_service(prefix="CLASS:")
        stage = declare_device(PrefixedDevice, service="beamline")

    app = App().build()

    assert component(app.devices, "stage", PrefixedDevice).prefix == "CLASS:"
