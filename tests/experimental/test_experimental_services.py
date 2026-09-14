"""A session starts its services first, hands devices their prefix, and connects them."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from ophyd_async.epics.core import EpicsDevice

from redsun.experimental import AsDevice, Declare, Session

if TYPE_CHECKING:
    from .conftest import BuildSession


class Camera(EpicsDevice):
    pass


def test_an_epics_device_builds_with_its_prefix(build: BuildSession) -> None:
    """A device whose first parameter is not ``name`` gets its name by keyword."""

    class App(Session):
        camera: Annotated[AsDevice[Camera], Declare(prefix="CAM:")]

    app = build(App)

    assert app.devices["camera"].name == "camera"
