"""A session starts its services first, hands devices their prefix, and connects them."""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Any, ClassVar, TypeAlias

import pytest
import yaml
from ophyd_async.core import (
    Device,
    DeviceConnector,
    NotConnectedError,
    SignalRW,
    StandardReadable,
    StandardReadableFormat,
    soft_signal_rw,
)
from ophyd_async.epics.core import EpicsDevice, PvSuffix

from redsun.aio import run_coro
from redsun.experimental import (
    Alias,
    AsDevice,
    AsPresenter,
    AsService,
    Attach,
    Declare,
    Launch,
    Session,
    slot,
)
from redsun.experimental.session import _base as session_base
from redsun.services import _service
from redsun.services._transports import PV_ACCESS, TRANSPORTS, PVAccess

if TYPE_CHECKING:
    from .conftest import BuildSession


STAND_IN = "mock_pkg.service.stand_in"
READY = "stand-in ready"
PVA_STAND_IN = "mock_pkg.service.pva_stand_in"
PVA_READY = "pva stand-in ready"


CameraIoc: TypeAlias = Annotated[
    AsService,
    Launch("mylab.iocs.camera", ready="Server startup complete.", prefix="CAM:"),
]


class Camera(EpicsDevice):
    exposure: Annotated[SignalRW[float], PvSuffix("Exposure")]


class CountingConnector(DeviceConnector):
    """Counts the connections made through it, and makes none."""

    def __init__(self) -> None:
        self.connections = 0

    async def connect_real(
        self, device: Device, timeout: float, force_reconnect: bool
    ) -> None:
        self.connections += 1


class RefusingConnector(DeviceConnector):
    async def connect_real(
        self, device: Device, timeout: float, force_reconnect: bool
    ) -> None:
        raise NotConnectedError("the camera did not answer")


class CountedDevice(Device):
    def __init__(self, name: str = "") -> None:
        self.connector = CountingConnector()
        super().__init__(name=name, connector=self.connector)


class RefusingDevice(Device):
    def __init__(self, prefix: str, name: str = "") -> None:
        super().__init__(name=name, connector=RefusingConnector())


class DeviceWithServiceKeyword(Device):
    def __init__(self, name: str = "", service: str = "") -> None:
        super().__init__(name=name)


class ExitWatcher:
    """Presenter recording each service exit it hears, and the thread it ran on."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.exits: list[tuple[str, int, str]] = []
        self.heard = threading.Event()

    @slot
    def on_exit(self, service: str, code: int) -> None:
        self.exits.append((service, code, threading.current_thread().name))
        self.heard.set()


class Broken(EpicsDevice):
    def __init__(self, prefix: str, name: str = "") -> None:
        raise ValueError("broken")


class SavedStage(StandardReadable):
    """Device on a service, saving the velocity its configuration signal holds."""

    def __init__(self, prefix: str, name: str = "", velocity: float = 1.0) -> None:
        with self.add_children_as_readables(StandardReadableFormat.CONFIG_SIGNAL):
            self.velocity = soft_signal_rw(float, initial_value=velocity)
        super().__init__(name=name)

    def serialize(self) -> dict[str, float]:
        return {"velocity": run_coro(self.velocity.get_value())}


class ServiceAndPrefix(Session):
    beamline: Annotated[AsService, Attach("BL01:")]
    device: Annotated[AsDevice[Camera], Declare(service="beamline", prefix="X:")]


class OwnServiceKeyword(Session):
    beamline: Annotated[AsService, Attach("BL01:")]
    device: Annotated[AsDevice[DeviceWithServiceKeyword], Declare(service="beamline")]


class AutoconnectNotBool(Session):
    device: Annotated[AsDevice[Camera], Declare(prefix="X:", autoconnect="yes")]


class DescribedWithDeclare(Session):
    ioc: Annotated[AsService, Declare(prefix="CAM:")]


class AttachedToAModule(Session):
    config: ClassVar[dict[str, Any]] = {
        "services": {"ioc": {"module": "mylab.iocs.camera"}}
    }
    ioc: Annotated[AsService, Attach("CAM:")]


def errors_in(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]


def summary_in(caplog: pytest.LogCaptureFixture) -> str:
    (summary,) = [m for m in caplog.messages if m.startswith("Container built")]
    return summary


def test_an_epics_device_builds_with_its_prefix(build: BuildSession) -> None:
    """A device whose first parameter is not ``name`` gets its name by keyword."""

    class App(Session):
        camera: Annotated[AsDevice[Camera], Declare(prefix="CAM:", autoconnect=False)]

    app = build(App)

    camera = app.devices["camera"]
    assert isinstance(camera, Camera)
    assert (camera.name, camera.exposure.source) == ("camera", "ca://CAM:Exposure")


def test_services_are_read_from_annotations_and_the_configuration() -> None:
    class App(Session):
        config: ClassVar[dict[str, Any]] = {
            "services": {
                "ioc": {"prefix": "FROM-FILE:", "stop_timeout": 2},
                "beamline": {"prefix": "BL01:"},
            }
        }
        ioc: CameraIoc
        motors: Annotated[AsService, Alias("stage_ioc"), Attach("MOT:")]

    app = App()
    app.read_configuration()

    services = app.services
    assert set(services) == {"ioc", "stage_ioc", "beamline"}
    ioc, stage_ioc = services["ioc"], services["stage_ioc"]
    assert (ioc.module, ioc.prefix, ioc.stop_timeout) == (
        "mylab.iocs.camera",
        "CAM:",
        2,
    )
    assert (stage_ioc.launched, stage_ioc.prefix) == (False, "MOT:")
    assert not services["beamline"].launched
    assert vars(app)["stage_ioc"] is stage_ioc


def test_a_marker_where_an_alias_is_used_replaces_the_alias_marker() -> None:
    class App(Session):
        spare: Annotated[CameraIoc, Launch("mylab.iocs.spare", prefix="SPARE:")]

    app = App()
    app.read_configuration()

    spare = app.services["spare"]
    assert (spare.module, spare.prefix, spare.ready) == (
        "mylab.iocs.spare",
        "SPARE:",
        None,
    )


def test_a_service_from_a_plugin_takes_its_module_and_readiness_line(
    mock_plugin: None,
) -> None:
    class App(Session):
        config: ClassVar[dict[str, Any]] = {
            "services": {
                "ioc": {
                    "plugin_name": "mock-bundle",
                    "plugin_id": "stand-in",
                    "prefix": "SIM:",
                }
            }
        }

    app = App()
    app.read_configuration()

    ioc = app.services["ioc"]
    assert (ioc.module, ioc.ready, ioc.prefix) == (STAND_IN, READY, "SIM:")


@pytest.mark.parametrize(
    ("config", "error"),
    [
        ({"services": {"ioc": {"launch": "attach"}}}, "launch"),
        ({"services": {"ioc": {"args": ["--x"]}}}, "no module to run"),
    ],
    ids=["unknown-key", "args-without-module"],
)
def test_a_service_the_session_cannot_make_is_refused(
    config: dict[str, Any], error: str
) -> None:
    class App(Session):
        pass

    with pytest.raises(TypeError, match=error):
        App(config).read_configuration()


@pytest.mark.parametrize(
    ("cls", "error"),
    [
        (DescribedWithDeclare, "Launch or Attach"),
        (AttachedToAModule, "gives a module to launch"),
    ],
    ids=["declare", "attach-with-module"],
)
def test_a_service_described_against_its_marker_is_refused(
    cls: type[Session], error: str
) -> None:
    with pytest.raises(TypeError, match=error):
        cls().read_configuration()


def test_a_service_named_like_a_session_attribute_is_refused() -> None:
    class App(Session):
        config: ClassVar[dict[str, Any]] = {"services": {"devices": {"prefix": "X:"}}}

    with pytest.raises(TypeError, match="'devices'"):
        App().read_configuration()


def test_a_service_named_like_a_component_is_refused() -> None:
    class App(Session):
        camera: Annotated[AsService, Attach("CAM:")]
        detector: Annotated[AsDevice[Camera], Alias("camera")]

    with pytest.raises(TypeError, match="'camera' as both a service and a component"):
        App().read_configuration()


def test_services_start_before_devices_and_stop_after_shutdown(
    build: BuildSession, launchable: None, tmp_path: Path
) -> None:
    marker = tmp_path / "cleaned"

    class App(Session):
        config: ClassVar[dict[str, Any]] = {
            "services": {"stand_in": {"args": ["--marker", str(marker)]}}
        }
        stand_in: Annotated[AsService, Launch(STAND_IN, ready=READY, prefix="SIM:")]
        camera: Annotated[
            AsDevice[Camera], Declare(service="stand_in", autoconnect=False)
        ]

    app = build(App)
    was_running = app.stand_in.running
    camera = app.devices["camera"]

    app.shutdown()

    assert isinstance(camera, Camera)
    assert camera.exposure.source == "ca://SIM:Exposure"
    assert (was_running, app.stand_in.running) == (True, False)
    assert marker.read_text() == "cleaned up"


def test_a_build_that_raises_stops_the_services_it_started(launchable: None) -> None:
    class App(Session):
        stand_in: Annotated[AsService, Launch(STAND_IN, ready=READY)]

        def wire(self) -> None:
            raise RuntimeError("wiring went wrong")

    app = App()
    with pytest.raises(RuntimeError, match="wiring went wrong"):
        app.build()

    assert not app.stand_in.running


def test_a_device_whose_service_is_missing_is_skipped(
    build: BuildSession, launchable: None, caplog: pytest.LogCaptureFixture
) -> None:
    class App(Session):
        config: ClassVar[dict[str, Any]] = {"services": {"unprefixed": {}}}
        broken: Annotated[
            AsService, Launch(STAND_IN, ready=READY, args=["--no-ready", "--exit", "3"])
        ]
        beamline: Annotated[AsService, Attach("BL01:")]
        camera: Annotated[AsDevice[Camera], Declare(service="broken")]
        typo: Annotated[AsDevice[Camera], Declare(service="beamlin")]
        bare: Annotated[AsDevice[Camera], Declare(service="unprefixed")]
        stage: Annotated[
            AsDevice[Camera], Declare(service="beamline", autoconnect=False)
        ]

    app = build(App)

    assert set(app.devices) == {"stage"}
    errors = errors_in(caplog)
    assert "Failed to build device 'camera': service 'broken' was not started" in errors
    assert "Failed to build device 'typo': service 'beamlin' is not declared" in errors
    assert (
        "Failed to build device 'bare': service 'unprefixed' gives no prefix" in errors
    )
    assert (
        "Services started: 2/3\nNot started: broken (exited with code 3 before it "
        "was ready)"
    ) in caplog.messages
    assert summary_in(caplog).splitlines()[-1] == "Unused: unprefixed (no device built)"


@pytest.mark.parametrize(
    ("cls", "reason"),
    [
        (ServiceAndPrefix, "and a prefix"),
        (OwnServiceKeyword, "'service' keyword"),
        (AutoconnectNotBool, "takes true or false"),
    ],
    ids=["service-and-prefix", "own-service-keyword", "autoconnect-not-bool"],
)
def test_a_device_declared_with_keywords_the_session_cannot_read_is_refused(
    cls: type[Session], reason: str
) -> None:
    with pytest.raises(TypeError, match=reason):
        cls().read_configuration()


def test_a_service_whose_every_device_failed_is_reported_unused(
    build: BuildSession, caplog: pytest.LogCaptureFixture
) -> None:
    class App(Session):
        beamline: Annotated[AsService, Attach("BL01:")]
        spare: Annotated[AsService, Attach("BL02:")]
        stages: Annotated[AsService, Attach("ST:")]
        broken: Annotated[AsDevice[Broken], Declare(service="beamline")]
        broken_stage: Annotated[AsDevice[Broken], Declare(service="stages")]
        stage: Annotated[AsDevice[Camera], Declare(service="stages", autoconnect=False)]

    build(App)

    assert summary_in(caplog).endswith("Unused: beamline (no device built)")


def test_a_saved_device_keeps_the_service_it_names(
    build: BuildSession, tmp_path: Path
) -> None:
    class App(Session):
        config: ClassVar[dict[str, Any]] = {
            "session": "saved",
            "services": {"beamline": {"prefix": "BL01:"}},
            "devices": {
                "stage": {"service": "beamline", "autoconnect": False, "velocity": 1.5}
            },
        }
        stage: AsDevice[SavedStage]

    written = yaml.safe_load(build(App).write(tmp_path / "saved.yaml").read_text())

    assert written["devices"]["stage"] == {
        "velocity": 1.5,
        "service": "beamline",
        "autoconnect": False,
    }


def test_a_session_built_again_starts_its_services_again(
    caplog: pytest.LogCaptureFixture,
) -> None:
    class App(Session):
        beamline: Annotated[AsService, Attach("BL01:")]

    app = App()
    app.build()
    app.shutdown()
    app.build()
    app.shutdown()

    started = [r for r in caplog.records if r.getMessage() == "Services started: 1/1"]
    assert len(started) == 2


def test_the_build_connects_devices_declared_with_autoconnect(
    build: BuildSession,
) -> None:
    class App(Session):
        motor: AsDevice[CountedDevice]
        idle: Annotated[AsDevice[CountedDevice], Declare(autoconnect=False)]

    app = build(App)

    counts = {
        name: device.connector.connections
        for name, device in app.devices.items()
        if isinstance(device, CountedDevice)
    }
    assert counts == {"motor": 1, "idle": 0}


def test_a_device_that_does_not_connect_is_skipped_naming_its_service(
    build: BuildSession,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(session_base, "CONNECT_TIMEOUT", 0.5)

    class App(Session):
        beamline: Annotated[AsService, Attach("BL01:")]
        camera: Annotated[AsDevice[RefusingDevice], Declare(service="beamline")]
        motor: AsDevice[CountedDevice]

    app = build(App)

    assert set(app.devices) == {"motor"}
    assert "camera" not in vars(app)
    assert (
        "Failed to connect device 'camera': service 'beamline' (attached) did not "
        "answer within 0.5 s: the camera did not answer"
    ) in errors_in(caplog)
    assert (
        "Not built: camera (device, not connected)" in summary_in(caplog).splitlines()
    )


def test_a_caproto_ioc_is_launched_and_its_device_read_while_building(
    build: BuildSession, launchable: None
) -> None:
    """The service is named as in the container tests, so it keeps libca's port."""

    class App(Session):
        ioc_a: Annotated[
            AsService,
            Launch(
                "mock_pkg.service.camera_ioc",
                ready="Server startup complete",
                prefix="A:",
                args=["--prefix", "A:"],
            ),
        ]
        camera: Annotated[AsDevice[Camera], Declare(service="ioc_a")]

    camera = build(App).devices["camera"]

    assert isinstance(camera, Camera)
    assert run_coro(camera.exposure.get_value()) == 0.25


def test_a_presenter_hears_a_service_exit_through_wire(
    build: BuildSession, launchable: None, tmp_path: Path
) -> None:
    exit_now = tmp_path / "exit-now"

    class App(Session):
        config: ClassVar[dict[str, Any]] = {
            "services": {
                "stand_in": {"args": ["--exit", "4", "--exit-when", str(exit_now)]}
            }
        }
        stand_in: Annotated[AsService, Launch(STAND_IN, ready=READY)]
        watcher: AsPresenter[ExitWatcher]

        def wire(self) -> None:
            self.connect(self.stand_in.sig_exited, self.watcher.on_exit)

    app = build(App)
    exit_now.touch()

    assert app.watcher.heard.wait(10)
    assert app.watcher.exits == [("stand_in", 4, "service-stand_in")]


def test_a_session_names_what_its_services_speak(build: BuildSession) -> None:
    """Named once, it reaches every service, annotated or listed only.

    A fragment layered under the source naming it needs no key of its own.
    """
    named = {"services": {"transport": "pv-access"}}
    fragment = {"services": {"beamline": {"prefix": "BL01:"}}}

    class App(Session):
        camera: Annotated[AsService, Attach("CAM:")]

    app = build(App, [named, fragment])

    assert app.transport == PV_ACCESS
    assert {s.transport for s in app.services.values()} == {PV_ACCESS}
    assert set(app.services) == {"camera", "beamline"}


def test_a_transport_redsun_does_not_have_is_refused() -> None:
    with pytest.raises(TypeError, match="carrier-pigeon"):
        Session({"services": {"transport": "carrier-pigeon"}}).build()


def test_a_service_named_transport_is_refused() -> None:
    """From the section, where the key is reserved, and from an annotation."""
    with pytest.raises(TypeError, match="reserved"):
        Session({"services": {"transport": {"prefix": "BL01:"}}}).build()

    class App(Session):
        transport: Annotated[AsService, Attach("BL01:")]  # type: ignore[assignment]

    with pytest.raises(TypeError, match="already an attribute"):
        App().build()


def test_two_pva_services_answer_on_the_loopback(
    build: BuildSession, launchable: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Both are kept local, and this process is told where to find them."""
    p4p = pytest.importorskip("p4p.client.thread")
    monkeypatch.setenv("EPICS_PVA_ADDR_LIST", "")
    monkeypatch.setitem(TRANSPORTS, PV_ACCESS, PVAccess())

    class App(Session):
        config: ClassVar[dict[str, Any]] = {
            "services": {
                "transport": "pv-access",
                "first": {"args": ["--pv", "SIM:FIRST", "--value", "1.0"]},
                "second": {"args": ["--pv", "SIM:SECOND", "--value", "2.0"]},
            }
        }
        first: Annotated[AsService, Launch(PVA_STAND_IN, ready=PVA_READY)]
        second: Annotated[AsService, Launch(PVA_STAND_IN, ready=PVA_READY)]

    build(App)

    assert os.environ["EPICS_PVA_ADDR_LIST"].split() == ["127.0.0.1"]
    with p4p.Context("pva") as client:
        assert float(client.get("SIM:FIRST", timeout=10.0)) == 1.0
        assert float(client.get("SIM:SECOND", timeout=10.0)) == 2.0


def test_layered_sources_must_agree_on_the_transport() -> None:
    under = {"services": {"transport": "channel-access"}}
    over = {"services": {"transport": "pv-access"}}

    with pytest.raises(ValueError, match="contradicts"):
        Session([under, over]).build()


def test_services_start_together(
    build: BuildSession,
    launchable: None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each stand-in is ready only once the other runs, so one at a time never is."""
    monkeypatch.setattr(_service, "STARTUP_TIMEOUT", 5.0)
    first, second = tmp_path / "first", tmp_path / "second"

    class App(Session):
        config: ClassVar[dict[str, Any]] = {
            "services": {
                "left": {"args": ["--touch", str(first), "--ready-when", str(second)]},
                "right": {"args": ["--touch", str(second), "--ready-when", str(first)]},
            }
        }
        left: Annotated[AsService, Launch(STAND_IN, ready=READY)]
        right: Annotated[AsService, Launch(STAND_IN, ready=READY)]

    app = build(App)

    assert (app.left.running, app.right.running) == (True, True)
