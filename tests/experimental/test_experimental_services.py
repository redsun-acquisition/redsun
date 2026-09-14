"""A session starts its services first, hands devices their prefix, and connects them."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any, ClassVar, TypeAlias

import pytest
from ophyd_async.epics.core import EpicsDevice

from redsun.experimental import (
    Alias,
    AsDevice,
    AsService,
    Attach,
    Declare,
    Launch,
    Session,
)

if TYPE_CHECKING:
    from .conftest import BuildSession


STAND_IN = "mock_pkg.service.stand_in"
READY = "stand-in ready"


CameraIoc: TypeAlias = Annotated[
    AsService,
    Launch("mylab.iocs.camera", ready="Server startup complete.", prefix="CAM:"),
]


class Camera(EpicsDevice):
    pass


class DescribedWithDeclare(Session):
    ioc: Annotated[AsService, Declare(prefix="CAM:")]


class AttachedToAModule(Session):
    config: ClassVar[dict[str, Any]] = {
        "services": {"ioc": {"module": "mylab.iocs.camera"}}
    }
    ioc: Annotated[AsService, Attach("CAM:")]


def test_an_epics_device_builds_with_its_prefix(build: BuildSession) -> None:
    """A device whose first parameter is not ``name`` gets its name by keyword."""

    class App(Session):
        camera: Annotated[AsDevice[Camera], Declare(prefix="CAM:")]

    app = build(App)

    assert app.devices["camera"].name == "camera"


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
