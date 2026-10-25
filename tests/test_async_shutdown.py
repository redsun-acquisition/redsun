"""Which `shutdown` a session calls when it shuts down, and in what order."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Annotated

import pytest
from ophyd_async.core import (
    Device,
    DeviceConnector,
    NotConnectedError,
    StandardReadable,
)

from redsun import AsDevice, AsPresenter, Declare, Session

if TYPE_CHECKING:
    from redsun.testing import BuildSession


class Laser(StandardReadable):
    """Device leaving its hardware in a safe state."""

    def __init__(
        self,
        name: str,
        shutdowns: list[str],
        connector: DeviceConnector | None = None,
    ) -> None:
        self.shutdowns = shutdowns
        super().__init__(name=name, connector=connector)

    async def shutdown(self) -> None:
        self.shutdowns.append(self.name)


class Refusing(DeviceConnector):
    """Connector of a device nothing answers for."""

    async def connect_real(
        self, device: Device, timeout: float, force_reconnect: bool
    ) -> None:
        raise NotConnectedError("no answer")


class Ctrl:
    """Presenter whose teardown awaits."""

    def __init__(self, name: str, shutdowns: list[str]) -> None:
        self.name = name
        self.shutdowns = shutdowns

    async def shutdown(self) -> None:
        self.shutdowns.append(self.name)


class Stuck:
    """Presenter whose teardown never ends unless cancelled."""

    def __init__(self, name: str, shutdowns: list[str]) -> None:
        self.name = name
        self.shutdowns = shutdowns

    async def shutdown(self) -> None:
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.shutdowns.append(f"{self.name} cancelled")
            raise


class App(Session):
    laser: AsDevice[Laser]
    ctrl: AsPresenter[Ctrl]


class StuckApp(Session):
    laser: AsDevice[Laser]
    stuck: AsPresenter[Stuck]


class Partial(Session):
    laser: AsDevice[Laser]
    unplugged: Annotated[AsDevice[Laser], Declare(connector=Refusing())]
    later: Annotated[AsDevice[Laser], Declare(autoconnect=False, connector=Refusing())]


@pytest.fixture
def shutdowns() -> list[str]:
    """Return the names of the components shut down, in order."""
    return []


def test_a_component_is_awaited_before_the_device_it_may_use(
    build: BuildSession, shutdowns: list[str]
) -> None:
    """Await a presenter's `shutdown` before that of the devices it may use."""
    app = build(
        App,
        {
            "devices": {"laser": {"shutdowns": shutdowns}},
            "presenters": {"ctrl": {"shutdowns": shutdowns}},
        },
    )

    app.shutdown()

    assert shutdowns == ["ctrl", "laser"]


def test_a_device_that_did_not_connect_is_not_shut_down(
    build: BuildSession, shutdowns: list[str]
) -> None:
    """Skip `shutdown` for a device that failed to connect, not one left unconnected."""
    app = build(
        Partial,
        {
            "devices": {
                name: {"shutdowns": shutdowns}
                for name in ("laser", "unplugged", "later")
            }
        },
    )
    assert set(app.devices) == {"laser", "later"}

    app.shutdown()

    assert sorted(shutdowns) == ["laser", "later"]


def test_a_teardown_that_does_not_end_is_cancelled_and_logged(
    build: BuildSession,
    shutdowns: list[str],
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancel an async `shutdown` still running after the wait, log it, and go on."""
    monkeypatch.setattr("redsun.session._base.SHUTDOWN_TIMEOUT", 0.1)
    app = build(
        StuckApp,
        {
            "devices": {"laser": {"shutdowns": shutdowns}},
            "presenters": {"stuck": {"shutdowns": shutdowns}},
        },
    )

    with caplog.at_level(logging.WARNING, logger="redsun"):
        app.shutdown()

    assert shutdowns == ["stuck cancelled", "laser"]
    assert "stuck did not shut down within 0.1 s; cancelled it" in caplog.messages
