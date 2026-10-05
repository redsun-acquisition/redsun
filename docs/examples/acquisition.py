"""A session running plans from the window with the built-in acquisition stack."""

from __future__ import annotations

from collections.abc import Iterator, Mapping  # noqa: TC003
from functools import cached_property
from typing import Any, ClassVar

import bluesky.plan_stubs as bps
from bluesky.protocols import Movable  # noqa: TC002
from bluesky.utils import MsgGenerator  # noqa: TC002
from ophyd_async.core import (
    MovableLogic,
    StandardMovable,
    StandardReadable,
    soft_signal_rw,
)

from redsun import AsDevice, AsPresenter, AsView, Link, PlanEntry  # noqa: TC001
from redsun.presenter import AcquisitionPresenter  # noqa: TC001
from redsun.qt import QtSession
from redsun.view.qt.builtins import AcquisitionView  # noqa: TC001


class MyMotor(StandardReadable, StandardMovable[float]):
    def __init__(self, name: str = "") -> None:
        with self.add_children_as_readables():
            self.position = soft_signal_rw(float, 0.0, units="mm")
        super().__init__(name=name)

    @cached_property
    def movable_logic(self) -> MovableLogic[float]:
        return MovableLogic(setpoint=self.position, readback=self.position)


# --8<-- [start:plans]
class MyPlans:
    def __init__(self, name: str) -> None:
        self.name = name

    def plan_map(self) -> Mapping[str, PlanEntry]:
        return {"walk": {"plan": self.walk}}

    def walk(
        self, motor: Movable[float], steps: int = 3, size: float = 1.0
    ) -> MsgGenerator[None]:
        """Move *motor* by *size* *steps* times."""
        for step in range(1, steps + 1):
            yield from bps.mv(motor, step * size)


# --8<-- [end:plans]
# --8<-- [start:session]
class MyApp(QtSession):
    config: ClassVar[dict[str, Any]] = {"session": "my-lab"}

    motor: AsDevice[MyMotor]
    plans: AsPresenter[MyPlans]
    acquisition: AsPresenter[AcquisitionPresenter]
    acquisition_view: AsView[AcquisitionView]

    def wire(self) -> Iterator[Link]:
        # --8<-- [start:wire]
        yield self.acquisition_view.sig_launch, self.acquisition.launch
        yield self.acquisition_view.sig_pause, self.acquisition.pause
        yield self.acquisition_view.sig_resume, self.acquisition.resume
        yield self.acquisition_view.sig_stop, self.acquisition.stop
        yield self.acquisition_view.sig_action, self.acquisition.request_action
        yield self.acquisition_view.sig_base_dir, self.acquisition.set_base_dir
        yield self.acquisition.sig_plan_started, self.acquisition_view.set_started
        yield self.acquisition.sig_plan_done, self.acquisition_view.set_done
        yield self.acquisition.sig_plan_failed, self.acquisition_view.set_failed
        yield self.acquisition.sig_progress, self.acquisition_view.update_progress
        yield self.acquisition.sig_action_changed, self.acquisition_view.update_action
        yield (
            self.acquisition.sig_base_dir_changed,
            self.acquisition_view.update_base_dir,
        )
        # --8<-- [end:wire]


if __name__ == "__main__":
    MyApp().run()
# --8<-- [end:session]
