"""Which `shutdown` a session calls when it shuts down, and in what order."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, ClassVar

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

    closed: ClassVar[list[str]] = []

    def __init__(self, name: str) -> None:
        super().__init__(name=name)

    async def shutdown(self) -> None:
        self.closed.append(self.name)


class Refusing(DeviceConnector):
    async def connect_real(
        self, device: Device, timeout: float, force_reconnect: bool
    ) -> None:
        raise NotConnectedError("no answer")


class Unplugged(Laser):
    """A laser nothing answers for."""

    def __init__(self, name: str) -> None:
        Device.__init__(self, name=name, connector=Refusing())


class Ctrl:
    """Presenter whose teardown awaits."""

    def __init__(self, name: str) -> None:
        self.name = name

    async def shutdown(self) -> None:
        Laser.closed.append(self.name)


class App(Session):
    laser: AsDevice[Laser]
    ctrl: AsPresenter[Ctrl]


class Partial(Session):
    laser: AsDevice[Laser]
    unplugged: AsDevice[Unplugged]
    later: Annotated[AsDevice[Unplugged], Declare(autoconnect=False)]


def test_a_component_is_awaited_before_the_device_it_may_use(
    build: BuildSession,
) -> None:
    """Await a presenter's `shutdown` before that of the devices it may use."""
    Laser.closed.clear()

    build(App).shutdown()

    assert Laser.closed == ["ctrl", "laser"]


def test_a_device_that_did_not_connect_is_not_shut_down(build: BuildSession) -> None:
    """Skip `shutdown` for a device that failed to connect, not one left unconnected."""
    Laser.closed.clear()
    app = build(Partial)
    assert set(app.devices) == {"laser", "later"}

    app.shutdown()

    assert sorted(Laser.closed) == ["laser", "later"]
