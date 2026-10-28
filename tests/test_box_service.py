"""A session launches a sharedbox service and connects a device to it."""

from __future__ import annotations

import subprocess
import sys
from typing import TYPE_CHECKING, Annotated, Any, ClassVar

from ophyd_async.core import Device, SignalRW

from redsun import AsDevice, AsService, Declare, Launch, Session
from redsun.aio import run_coro
from redsun.device.sharedbox import BoxDeviceConnector
from tests.sdk.helpers import kept_under

if TYPE_CHECKING:
    from pathlib import Path

    from redsun.testing import BuildSession

BOX_STAND_IN = "mock_pkg.service.box_stand_in"
BOX_READY = "box stand-in ready"

NO_SERVICES = """
import sys
from redsun import Session

Session().build().shutdown()
print([m for m in ("sharedbox", "fastcs") if m in sys.modules])
"""


class Detector(Device):
    """A device whose children come from the service's index."""

    exposure: SignalRW[float]

    def __init__(self, prefix: str, name: str = "") -> None:
        super().__init__(name=name, connector=BoxDeviceConnector(prefix))


class BoxApp(Session):
    config: ClassVar[dict[str, Any]] = {"services": {"transport": "sharedbox"}}
    box_service: Annotated[
        AsService, Launch(BOX_STAND_IN, ready=BOX_READY, prefix="BOXSVC")
    ]
    detector: Annotated[AsDevice[Detector], Declare(service="box_service")]


def test_a_session_builds_a_device_from_a_box_service(
    build: BuildSession, launchable: None
) -> None:
    """Launch the service, connect the declared device and round-trip a set."""
    app = build(BoxApp)
    detector = app.devices["detector"]
    assert isinstance(detector, Detector)

    async def round_trip() -> None:
        await detector.exposure.set(2.5)
        assert await detector.exposure.get_value() == 2.5

    run_coro(round_trip())


def test_a_session_without_sharedbox_loads_neither_sharedbox_nor_fastcs(
    tmp_path: Path,
) -> None:
    """Import neither package while building a session with no services."""
    ran = subprocess.run(
        [sys.executable, "-c", kept_under(tmp_path) + NO_SERVICES],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    assert ran.returncode == 0, ran.stderr
    assert ran.stdout.strip().endswith("[]")
