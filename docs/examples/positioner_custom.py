"""The customized session of the guide "How to move devices by hand"."""

from __future__ import annotations

from collections.abc import Iterator  # noqa: TC003
from dataclasses import dataclass, field
from functools import cached_property
from typing import Annotated, Any, ClassVar

from ophyd_async.core import (
    DeviceMap,
    MovableLogic,
    StandardMovable,
    StandardReadable,
    StandardReadableFormat,
    soft_signal_rw,
)
from qtpy.QtWidgets import QLabel, QPushButton

from redsun import (
    AsDevice,
    AsPresenter,
    AsView,
    Declare,
    Link,
    Settings,
    links_between,
)
from redsun.presenter import (
    DescribesAxes,
    PositionerPresenter,
)
from redsun.qt import QtSession
from redsun.view.qt.builtins import PositionerGroup, PositionerView


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


# --8<-- [start:presenter]
@dataclass(eq=False, kw_only=True)
class KeepOutPositioner(PositionerPresenter):
    keep_out: dict[str, tuple[float, float]] = field(default_factory=dict)

    def check(self, device: str, axis: str, target: float) -> None:
        super().check(device, axis, target)
        zone = self.keep_out.get(f"{device}.{axis}")
        if zone is not None and zone[0] <= target <= zone[1]:
            raise ValueError(f"{axis} {target} is in a keep-out zone")


# --8<-- [end:presenter]
# --8<-- [start:view]
class HomingGroup(PositionerGroup):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.home = QPushButton("Home", self)
        layout = self.layout()
        if layout is not None:
            layout.addWidget(self.home)


class MyPositionerView(PositionerView):
    group_class = HomingGroup

    def setup(self, positioner: DescribesAxes, settings: Settings) -> None:
        super().setup(positioner, settings)
        self.tabs.addTab(QLabel("Notes about this stage."), "Notes")


# --8<-- [end:view]
class MyApp(QtSession):
    config: ClassVar[dict[str, Any]] = {"session": "my-lab"}

    stage: AsDevice[MyStage]
    # --8<-- [start:declare]
    positioner: Annotated[
        AsPresenter[KeepOutPositioner], Declare(keep_out={"stage.x": (40.0, 60.0)})
    ]
    positioner_view: AsView[MyPositionerView]
    # --8<-- [end:declare]

    def wire(self) -> Iterator[Link]:
        yield from links_between(self.positioner_view, self.positioner)
