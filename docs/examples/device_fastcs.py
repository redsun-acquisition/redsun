"""The session of the guide "How to write a service with FastCS"."""

from __future__ import annotations

from collections.abc import Iterator, Mapping  # noqa: TC003
from typing import Annotated, Any, ClassVar, Protocol

from bluesky.protocols import Reading  # noqa: TC002
from ophyd_async.core import Device, SignalRW
from ophyd_async.fastcs.core import fastcs_connector
from psygnal import Signal
from qtpy.QtWidgets import QFormLayout, QLabel, QPushButton, QWidget

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
    def __init__(
        self, name: str, *, stages: DevicesOf[HasPosition], step: float = 1.0
    ) -> None:
        self.name = name
        self.stages = stages
        self.step = step

    @slot
    async def nudge(self, stage: str) -> None:
        position = await self.stages[stage].position.get_value()
        await self.stages[stage].position.set(position + self.step)


class StageView(QWidget):
    placement: Placement = Dock("left")
    sig_nudge = Signal(str)

    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.name = name
        self.rows = QFormLayout(self)
        self.labels: dict[str, QLabel] = {}

    def add_row(self, stage: str) -> None:
        button = QPushButton(f"Nudge {stage}")
        button.clicked.connect(lambda: self.sig_nudge.emit(stage))
        self.labels[stage] = QLabel()
        self.rows.addRow(button, self.labels[stage])

    @slot
    def show_reading(self, reading: dict[str, Reading[float]]) -> None:
        for signal, entry in reading.items():
            stage = signal.removesuffix("-position")
            if stage not in self.labels:
                self.add_row(stage)
            self.labels[stage].setText(f"position: {entry['value']}")


# --8<-- [start:session]
# --8<-- [start:declare]
class MyApp(QtSession):
    config: ClassVar[Mapping[str, Any]] = {"services": {"transport": "pv-access"}}

    stage_service: Annotated[
        AsService, Launch("stage_fastcs", ready="stage ready", prefix="STAGE:")
    ]
    stage: Annotated[AsDevice[MyStage], Declare(service="stage_service")]
    # --8<-- [end:declare]
    stage_ctrl: AsPresenter[StagePresenter]
    stage_view: AsView[StageView]

    def wire(self) -> Iterator[Link]:
        yield self.stage_view.sig_nudge, self.stage_ctrl.nudge
        yield self.stage.position, self.stage_view.show_reading


if __name__ == "__main__":
    MyApp().run()
# --8<-- [end:session]
