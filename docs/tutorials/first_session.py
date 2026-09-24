# /// script
# requires-python = ">=3.11"
# dependencies = ["redsun[pyqt]>=0.14"]
# ///
"""The session built in the "Writing your first session" tutorial."""

from __future__ import annotations

from ophyd_async.core import StandardReadable, soft_signal_rw
from psygnal import Signal
from qtpy.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from redsun import AsDevice, AsPresenter, AsView, DeviceMapping, Placement, slot
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
    sig_moved = Signal(float)

    def __init__(self, name: str, *, devices: DeviceMapping, step: float = 1.0) -> None:
        self.name = name
        self.stage = devices["stage"]
        self.step = step

    @slot
    async def nudge(self) -> None:
        position = await self.stage.position.get_value()
        await self.stage.position.set(position + self.step)
        self.sig_moved.emit(position + self.step)


# --8<-- [end:presenter]
# --8<-- [start:view]
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


# --8<-- [end:view]
# --8<-- [start:session]
class FirstSession(QtSession):
    stage: AsDevice[MyStage]
    stage_ctrl: AsPresenter[StagePresenter]
    stage_view: AsView[StageView]

    def wire(self) -> None:
        self.connect(self.stage_view.sig_nudge, self.stage_ctrl.nudge)
        self.connect(self.stage_ctrl.sig_moved, self.stage_view.show_position)


if __name__ == "__main__":
    FirstSession().run()
# --8<-- [end:session]
