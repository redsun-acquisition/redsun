# /// script
# requires-python = ">=3.11"
# dependencies = ["redsun[pyqt]>=0.14", "fastcs[epicspva]", "ophyd-async[pva]"]
# ///
"""The session of the guide "How to write a service with FastCS"."""

from __future__ import annotations

from collections.abc import Iterator, Mapping  # noqa: TC003
from typing import Annotated, Any, ClassVar, Protocol

from ophyd_async.core import Device, SignalRW
from ophyd_async.fastcs.core import fastcs_connector
from psygnal import Signal
from qtpy.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from redsun import (
    AsDevice,
    AsPresenter,
    AsService,
    AsView,
    Declare,
    DevicesOf,
    Launch,
    Link,
    Placement,
    slot,
)
from redsun.qt import Dock, QtSession


# --8<-- [start:device]
class MyStage(Device):
    position: SignalRW[float]

    def __init__(self, prefix: str, name: str = "") -> None:
        super().__init__(name=name, connector=fastcs_connector(prefix, self))


# --8<-- [end:device]
class HasPosition(Protocol):
    position: SignalRW[float]


class StagePresenter:
    sig_moved = Signal(float)

    def __init__(
        self, name: str, *, stages: DevicesOf[HasPosition], step: float = 1.0
    ) -> None:
        self.name = name
        self.stage = stages["stage"]
        self.step = step

    @slot
    async def nudge(self) -> None:
        position = await self.stage.position.get_value()
        await self.stage.position.set(position + self.step)
        self.sig_moved.emit(position + self.step)


class StageView(QWidget):
    placement: Placement = Dock("left")
    sig_nudge = Signal()

    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.name = name
        button = QPushButton("Nudge")
        button.clicked.connect(self.sig_nudge.emit)
        self.label = QLabel("position: 0.0")
        layout = QVBoxLayout(self)
        layout.addWidget(button)
        layout.addWidget(self.label)

    @slot
    def show_position(self, position: float) -> None:
        self.label.setText(f"position: {position}")


# --8<-- [start:session]
class MyApp(QtSession):
    config: ClassVar[Mapping[str, Any]] = {"services": {"transport": "pv-access"}}

    stage_service: Annotated[
        AsService, Launch("stage_fastcs", ready="stage ready", prefix="STAGE:")
    ]
    stage: Annotated[AsDevice[MyStage], Declare(service="stage_service")]
    stage_ctrl: AsPresenter[StagePresenter]
    stage_view: AsView[StageView]

    def wire(self) -> Iterator[Link]:
        yield self.stage_view.sig_nudge, self.stage_ctrl.nudge
        yield self.stage_ctrl.sig_moved, self.stage_view.show_position


if __name__ == "__main__":
    MyApp().run()
# --8<-- [end:session]
