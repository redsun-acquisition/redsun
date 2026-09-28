"""The session built in the "Building controls for a plan" tutorial."""

from __future__ import annotations

from collections.abc import Iterator, Mapping  # noqa: TC003
from typing import Any, Protocol, runtime_checkable

import bluesky.plan_stubs as bps
from bluesky.protocols import Reading  # noqa: TC002
from bluesky.utils import MsgGenerator  # noqa: TC002
from ophyd_async.core import SignalRW, StandardReadable, soft_signal_rw
from psygnal import Signal
from qtpy.QtWidgets import (
    QComboBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from redsun import (
    AsDevice,
    AsPresenter,
    AsView,
    CallbackType,
    DeviceMapping,
    DevicesOf,
    HasPlans,
    Link,
    Placement,
    PlanEntry,
    slot,
)
from redsun.engine import RunEngine
from redsun.presenter.plan_spec import (
    PlanSpec,
    collect_arguments,
    create_plan_spec,
    resolve_arguments,
)
from redsun.qt import Dock, QtSession
from redsun.view.qt.utils import PlanWidget, create_plan_widget


class MyStage(StandardReadable):
    def __init__(self, name: str = "", *, units: str = "mm") -> None:
        with self.add_children_as_readables():
            self.position = soft_signal_rw(float, units=units)
        super().__init__(name=name)


class FastStage(StandardReadable):
    def __init__(self, name: str = "", *, units: str = "mm") -> None:
        with self.add_children_as_readables():
            self.position = soft_signal_rw(float, initial_value=5.0, units=units)
            self.speed = soft_signal_rw(float, initial_value=10.0)
        super().__init__(name=name)


@runtime_checkable
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


# --8<-- [start:stage_plans]
class StagePlans:
    def __init__(self, name: str) -> None:
        self.name = name

    def walk(
        self, stage: HasPosition, steps: int = 5, size: float = 1.0
    ) -> MsgGenerator[None]:
        for _ in range(steps):
            position = yield from bps.rd(stage.position)
            yield from bps.mv(stage.position, position + size)

    def plan_map(self) -> Mapping[str, PlanEntry]:
        return {"walk": {"plan": self.walk}}


# --8<-- [end:stage_plans]


# --8<-- [start:plan_ctrl]
class PlanPresenter:
    sig_started = Signal(str)
    sig_finished = Signal()

    def __init__(self, name: str, *, devices: DeviceMapping) -> None:
        self.name = name
        self.devices = devices
        self.engine = RunEngine()
        self.plans: dict[str, PlanEntry] = {}
        self.specs: dict[str, PlanSpec] = {}

    def setup(
        self,
        providers: Mapping[str, HasPlans],
        callbacks: Mapping[str, CallbackType],
    ) -> None:
        for component in providers.values():
            self.plans.update(component.plan_map())
        for plan, entry in self.plans.items():
            self.specs[plan] = create_plan_spec(entry["plan"], self.devices)
        for callback in callbacks.values():
            self.engine.subscribe(callback)

    @slot
    def run(self, plan: str, values: dict[str, Any]) -> None:
        resolved = resolve_arguments(self.specs[plan], values, self.devices)
        args, kwargs = collect_arguments(self.specs[plan], resolved)
        self.sig_started.emit(plan)
        future = self.engine(self.plans[plan]["plan"](*args, **kwargs))
        future.add_done_callback(lambda _: self.sig_finished.emit())


# --8<-- [end:plan_ctrl]


# --8<-- [start:plan_view]
class PlanView(QWidget):
    placement: Placement = Dock("right")
    sig_run = Signal(str, dict)

    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.name = name
        self.chooser = QComboBox()
        self.pages = QStackedWidget()
        self.chooser.currentIndexChanged.connect(self.pages.setCurrentIndex)
        layout = QVBoxLayout(self)
        layout.addWidget(self.chooser)
        layout.addWidget(self.pages)
        self.widgets: dict[str, PlanWidget] = {}

    def setup(self, providers: Mapping[str, HasPlans], devices: DeviceMapping) -> None:
        for component in providers.values():
            for entry in component.plan_map().values():
                self.add_plan(create_plan_spec(entry["plan"], devices))

    def add_plan(self, spec: PlanSpec) -> None:
        widget = create_plan_widget(
            spec, run_callback=lambda: self.ask_to_run(spec.name)
        )
        self.widgets[spec.name] = widget
        self.chooser.addItem(spec.name)
        self.pages.addWidget(widget.group_box)

    def ask_to_run(self, plan: str) -> None:
        self.setEnabled(False)
        self.sig_run.emit(plan, self.widgets[plan].parameters)

    @slot
    def on_finished(self) -> None:
        self.setEnabled(True)


# --8<-- [end:plan_view]


# --8<-- [start:session]
class FirstSession(QtSession):
    stage: AsDevice[MyStage]
    fast_stage: AsDevice[FastStage]
    stage_ctrl: AsPresenter[StagePresenter]
    stage_plans: AsPresenter[StagePlans]
    plan_ctrl: AsPresenter[PlanPresenter]
    stage_view: AsView[StageView]
    plan_view: AsView[PlanView]

    def wire(self) -> Iterator[Link]:
        yield self.stage_view.sig_nudge, self.stage_ctrl.nudge
        yield self.stage.position, self.stage_view.show_reading
        yield self.fast_stage.position, self.stage_view.show_reading
        yield self.plan_view.sig_run, self.plan_ctrl.run
        yield self.plan_ctrl.sig_finished, self.plan_view.on_finished


if __name__ == "__main__":
    FirstSession().run()
# --8<-- [end:session]
