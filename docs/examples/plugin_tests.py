"""The tests of the guide "How to test a plugin"."""

from __future__ import annotations

from typing import TYPE_CHECKING

from docs.examples.connect_on_demand import MyApp
from docs.examples.device_fastcs import MyStage
from redsun import Launch

if TYPE_CHECKING:
    from qtpy.QtWidgets import QApplication

    from redsun.testing import BuildSession, StartService

# --8<-- [start:declare]
STAGE = Launch("stage_fastcs", ready="stage ready", prefix="STAGE:")
# --8<-- [end:declare]


# --8<-- [start:build]
def test_the_session_builds_every_component(
    build: BuildSession, qapp: QApplication
) -> None:
    """Build every component of the session, its devices mocked."""
    session = build(MyApp, {"mock": True, "strict": True})

    assert set(session.devices) == {"motor"}
    assert set(session.presenters) == {"ctrl"}
    assert set(session.views) == {"panel"}


# --8<-- [end:build]
# --8<-- [start:service]
async def test_the_stage_moves(start_service: StartService) -> None:
    """Move the stage its service serves."""
    service = start_service("stage_service", STAGE, transport="pv-access")
    stage = MyStage(service.prefix, name="stage")
    await stage.connect()

    await stage.position.set(2.0)

    assert await stage.position.get_value() == 2.0


# --8<-- [end:service]
