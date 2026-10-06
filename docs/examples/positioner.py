"""The session of the guide "How to move devices by hand"."""

from __future__ import annotations

from collections.abc import Iterator  # noqa: TC003
from functools import cached_property
from typing import Any, ClassVar

from ophyd_async.core import (
    DeviceMap,
    MovableLogic,
    StandardMovable,
    StandardReadable,
    StandardReadableFormat,
    soft_signal_rw,
)

from redsun import AsDevice, AsPresenter, AsView, Link, links_between
from redsun.engine import RunEngine
from redsun.presenter import PositionerPresenter  # noqa: TC001
from redsun.qt import QtSession
from redsun.view.qt.builtins import PositionerView  # noqa: TC001


# --8<-- [start:device]
class MyAxis(StandardReadable, StandardMovable[float]):
    def __init__(self, name: str = "") -> None:
        with self.add_children_as_readables(StandardReadableFormat.HINTED_SIGNAL):
            self.position = soft_signal_rw(float, 0.0, units="um", precision=2)
        with self.add_children_as_readables(StandardReadableFormat.CONFIG_SIGNAL):
            self.velocity = soft_signal_rw(float, 100.0, units="um/s")
        super().__init__(name=name)

    @cached_property
    def movable_logic(self) -> MovableLogic[float]:
        return MovableLogic(setpoint=self.position, readback=self.position)


class MyStage(StandardReadable):
    def __init__(self, name: str = "") -> None:
        self.axis = DeviceMap({"x": MyAxis(), "y": MyAxis()})
        self.add_readables(list(self.axis.values()))
        super().__init__(name=name)


# --8<-- [end:device]
class MyController:
    def __init__(self, name: str) -> None:
        self.name = name
        self.engine = RunEngine()


# --8<-- [start:session]
class MyApp(QtSession):
    config: ClassVar[dict[str, Any]] = {"session": "my-lab"}

    stage: AsDevice[MyStage]
    ctrl: AsPresenter[MyController]
    positioner: AsPresenter[PositionerPresenter]
    positioner_view: AsView[PositionerView]

    def wire(self) -> Iterator[Link]:
        # --8<-- [start:wire]
        yield from links_between(self.positioner_view, self.positioner)
        # --8<-- [end:wire]
        # --8<-- [start:wire-locks]
        yield self.ctrl.engine.sig_locks_changed, self.positioner_view.set_locked
        yield self.ctrl.engine.sig_locks_changed, self.positioner.set_locked
        # --8<-- [end:wire-locks]


if __name__ == "__main__":
    MyApp().run()
# --8<-- [end:session]
