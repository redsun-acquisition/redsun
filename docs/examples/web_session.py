"""The session of the guide "How to serve a session over the web"."""

from __future__ import annotations

from typing import ClassVar, Protocol

from ophyd_async.core import SignalRW, StandardReadable, soft_signal_rw
from psygnal import Signal

from redsun import AsDevice, AsPresenter, DevicesOf, Session, remote, slot
from redsun.fastapi import FastAPISession, RemoteSettings


class MyMotor(StandardReadable):
    def __init__(self, name: str = "") -> None:
        with self.add_children_as_readables():
            self.position = soft_signal_rw(float, 0.0, units="mm")
        super().__init__(name=name)


class HasPosition(Protocol):
    position: SignalRW[float]


# --8<-- [start:controller]
class MyController:
    sig_moved = Signal(str, float)

    def __init__(self, name: str, *, motors: DevicesOf[HasPosition]) -> None:
        self.name = name
        self.motors = motors

    @property
    @remote
    def names(self) -> list[str]:
        return sorted(self.motors)

    @slot
    @remote
    async def move_to(self, motor: str, position: float) -> float:
        await self.motors[motor].position.set(position)
        reached: float = await self.motors[motor].position.get_value()
        self.sig_moved.emit(motor, reached)
        return reached


# --8<-- [end:controller]
# --8<-- [start:core]
class MyCore(Session):
    stage: AsDevice[MyMotor]
    ctrl: AsPresenter[MyController]


# --8<-- [end:core]
# --8<-- [start:session]
class MyApp(FastAPISession, MyCore):
    remote: ClassVar[RemoteSettings] = {"origins": ["http://localhost:5173"]}


if __name__ == "__main__":
    MyApp().serve()
# --8<-- [end:session]
