"""The session built in the "Describing a device with a protocol" tutorial."""

from __future__ import annotations

from collections.abc import Iterator  # noqa: TC003
from typing import Protocol, runtime_checkable

from bluesky.protocols import Reading  # noqa: TC002
from ophyd_async.core import SignalRW, StandardReadable, soft_signal_rw
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
    DevicesOf,
    Link,
    Placement,
    slot,
)
from redsun.qt import Dock, QtSession


class MyStage(StandardReadable):
    def __init__(self, name: str = "", *, units: str = "mm") -> None:
        with self.add_children_as_readables():
            self.position = soft_signal_rw(float, units=units)
        super().__init__(name=name)


# --8<-- [start:device]
class FastStage(StandardReadable):
    def __init__(self, name: str = "", *, units: str = "mm") -> None:
        with self.add_children_as_readables():
            self.position = soft_signal_rw(float, initial_value=5.0, units=units)
            self.speed = soft_signal_rw(float, initial_value=10.0)
        super().__init__(name=name)


# --8<-- [end:device]


# --8<-- [start:protocol]
@runtime_checkable
class HasPosition(Protocol):
    position: SignalRW[float]


# --8<-- [end:protocol]


class StagePresenter:
    # --8<-- [start:constructor]
    def __init__(
        self, name: str, *, stages: DevicesOf[HasPosition], step: float = 1.0
    ) -> None:
        self.name = name
        self.stages = stages
        self.step = step

    # --8<-- [end:constructor]
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
class FirstSession(QtSession):
    stage: AsDevice[MyStage]
    fast_stage: AsDevice[FastStage]
    stage_ctrl: AsPresenter[StagePresenter]
    stage_view: AsView[StageView]

    def wire(self) -> Iterator[Link]:
        yield self.stage_view.sig_nudge, self.stage_ctrl.nudge
        yield self.stage.position, self.stage_view.show_reading
        yield self.fast_stage.position, self.stage_view.show_reading


if __name__ == "__main__":
    FirstSession().run()
# --8<-- [end:session]
