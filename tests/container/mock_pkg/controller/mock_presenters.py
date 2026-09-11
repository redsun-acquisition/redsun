from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any, cast

from ophyd_async.core import Device
from psygnal import Signal, SignalGroup

from redsun.presenter import Presenter
from redsun.virtual import VirtualContainer, slot

from ..device import MyMotor


class MockController(Presenter):
    def __init__(
        self,
        name: str,
        devices: Mapping[str, Device],
        /,
        string: str = "",
        integer: int = 0,
        floating: float = 0.0,
        boolean: bool = False,
    ) -> None:
        super().__init__(name, devices)
        self.string = string
        self.integer = integer
        self.floating = floating
        self.boolean = boolean
        self.moved: list[tuple[str, float]] = []

    @slot
    def on_motor_moved(self, motor: str, position: float) -> None:
        self.moved.append((motor, position))

    @slot
    def on_too_many(self, motor: str, position: float, extra: int) -> None: ...

    def not_connectable(self, motor: str, position: float) -> None: ...


class BrokenController(Presenter):
    """Declares the ports of a working presenter and never gets to expose them."""

    sig_motor_moved = Signal(str, float)

    def __init__(
        self,
        name: str,
        devices: Mapping[str, Device],
        /,
        string: str = "",
        integer: int = 0,
        floating: float = 0.0,
        boolean: bool = False,
    ) -> None:
        raise RuntimeError("Broken controller")

    @slot
    def on_motor_moved(self, motor: str, position: float) -> None: ...


class AsyncMotorController(Presenter):
    """Presenter whose coroutine slot moves a motor on the shared loop.

    A negative position raises, so that failures inside a dispatched slot
    can be observed.
    """

    sig_motor_moved = Signal(str, float)

    def __init__(
        self,
        name: str,
        devices: Mapping[str, Device],
        /,
        **_: Any,
    ) -> None:
        super().__init__(name, devices)
        self.moves: list[tuple[str, float]] = []
        self.loops: list[asyncio.AbstractEventLoop] = []
        self.shutdown_calls = 0

    def register_providers(self, container: VirtualContainer) -> None:
        container.register_signals(self)

    @slot
    async def move(self, motor: str, position: float) -> None:
        if position < 0:
            raise ValueError(f"{motor} position out of range: {position}")
        self.loops.append(asyncio.get_running_loop())
        await cast("MyMotor", self.devices[motor]).floating.set(position)
        self.moves.append((motor, position))
        self.sig_motor_moved.emit(motor, position)

    def shutdown(self) -> None:
        self.shutdown_calls += 1


class FrameSignals(SignalGroup, strict=True):
    """Two signals of one shape, addressed by their member names."""

    median = Signal(object)
    filtered = Signal(object)


class GroupedController(Presenter):
    """Presenter whose signals live in a group rather than on the class."""

    def __init__(self, name: str, devices: Mapping[str, Device], /, **_: Any) -> None:
        super().__init__(name, devices)
        self.frames = FrameSignals(instance=self)
        self.seen: list[Any] = []

    @slot
    def absorb(self, payload: Any) -> None:
        self.seen.append(payload)
