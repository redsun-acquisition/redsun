"""A `shutdown` that is a coroutine is awaited when the session shuts down."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from ophyd_async.core import StandardReadable

from redsun import AsDevice, AsPresenter, Session

if TYPE_CHECKING:
    from .conftest import BuildSession


class Laser(StandardReadable):
    """Device leaving its hardware in a safe state."""

    closed: ClassVar[list[str]] = []

    def __init__(self, name: str) -> None:
        super().__init__(name=name)

    async def shutdown(self) -> None:
        self.closed.append(self.name)


class Ctrl:
    """Presenter whose teardown awaits."""

    def __init__(self, name: str) -> None:
        self.name = name

    async def shutdown(self) -> None:
        Laser.closed.append(self.name)


class App(Session):
    laser: AsDevice[Laser]
    ctrl: AsPresenter[Ctrl]


def test_a_component_is_awaited_before_the_device_it_may_use(
    build: BuildSession,
) -> None:
    Laser.closed.clear()

    build(App).shutdown()

    assert Laser.closed == ["ctrl", "laser"]
