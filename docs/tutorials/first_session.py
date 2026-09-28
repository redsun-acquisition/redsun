"""The session built in the "Writing your first session" tutorial."""

from __future__ import annotations

from collections.abc import Iterator  # noqa: TC003

from bluesky.protocols import Reading  # noqa: TC002
from ophyd_async.core import StandardReadable, soft_signal_rw
from psygnal import Signal
from qtpy.QtWidgets import (
    QFormLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from redsun import (
    AsDevice,
    AsPresenter,
    AsView,
    DeviceMapping,
    Link,
    Placement,
    slot,
)
from redsun.qt import Dock, QtSession


# --8<-- [start:device]
class MyStage(StandardReadable):
    def __init__(self, name: str = "", *, units: str = "mm") -> None:
        with self.add_children_as_readables():
            self.position = soft_signal_rw(float, units=units)
        super().__init__(name=name)


# --8<-- [end:device]


# --8<-- [start:presenter]
class StagePresenter:
    def __init__(self, name: str, *, devices: DeviceMapping, step: float = 1.0) -> None:
        self.name = name
        self.stages = devices
        self.step = step

    @slot
    async def nudge(self, stage: str) -> None:
        position = await self.stages[stage].position.get_value()
        await self.stages[stage].position.set(position + self.step)


# --8<-- [end:presenter]


# --8<-- [start:view]
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


# --8<-- [end:view]


# --8<-- [start:session]
class FirstSession(QtSession):
    stage: AsDevice[MyStage]
    stage_ctrl: AsPresenter[StagePresenter]
    stage_view: AsView[StageView]

    def wire(self) -> Iterator[Link]:
        yield self.stage_view.sig_nudge, self.stage_ctrl.nudge
        yield self.stage.position, self.stage_view.show_reading


if __name__ == "__main__":
    FirstSession().run()
# --8<-- [end:session]
