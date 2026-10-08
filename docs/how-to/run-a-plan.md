---
icon: lucide/play
---

# How to run a plan from a presenter

Running a [plan](../explanation/glossary.md#plan) takes three components: one
offers the plan, a presenter runs it on a
[`RunEngine`](../explanation/glossary.md#runengine), and a view shows its
[plan widget](../explanation/glossary.md#plan-widget). Step through what the
three components of this guide do, from the build to the end of a plan:

```d2 title="From setup to a finished plan"
...@diagrams/style
label: "In setup, plan_ctrl asks ctrl for its plans with plan_map."
shape: sequence_diagram
plan_view: "plan_view\nPlanView" {class: step}
plan_ctrl: "plan_ctrl\nPlanPresenter" {
  class: step
  tooltip: Owns the RunEngine.
}
ctrl: "ctrl\nMyController" {
  class: step
  tooltip: Offers its plans through plan_map.
}
motor: "motor\nMyMotor" {class: step}
plan_ctrl -> ctrl: "setup: plan_map()"
plan_view -> ctrl: "setup: plan_map(),\nthen a plan widget each" {
  style.opacity: 0
}
plan_view -> plan_ctrl: "Run pressed: the view disables\nitself, sig_run(plan, values)" {
  style.opacity: 0
}
plan_ctrl -> motor: "the RunEngine runs the\nplan, which moves the motor" {
  style.opacity: 0
}
plan_ctrl -> plan_view: "sig_finished, whether the\nplan succeeded or failed" {
  style.opacity: 0
}
plan_view -> plan_view: "enable the view" {style.opacity: 0}
steps: {
  1: {label: "plan_view asks ctrl for its plans too, and builds a plan widget for each."; (plan_view -> ctrl)[0].style.opacity: 1}
  2: {label: "When the user presses Run, plan_view disables itself and emits sig_run with the plan's name and the values of its inputs."; (plan_view -> plan_ctrl)[0].style.opacity: 1}
  3: {label: "plan_ctrl runs the plan on its RunEngine, and the plan moves the motor."; (plan_ctrl -> motor)[0].style.opacity: 1}
  4: {label: "When the plan ends, whether it succeeded or failed, plan_ctrl emits sig_finished."; (plan_ctrl -> plan_view)[0].style.opacity: 1}
  5: {label: "plan_view enables itself again, ready for the next run."; (plan_view -> plan_view)[0].style.opacity: 1}
}
```

[How presenters run plans](../explanation/plans.md) explains how the three
components work together.

## Prerequisites

You need a Qt session with a device for the plan to move. Here it is `MyMotor`,
a device with a `position` signal. The tutorial
[Building controls for a plan](../tutorials/plan-controls.md) builds the same
three components one step at a time.

## Offer the plans

Give the component a `plan_map` method that returns each plan under its name,
as a [`PlanEntry`][redsun.PlanEntry]. A component with that method satisfies
[`HasPlans`][redsun.HasPlans]:

```python
from collections.abc import Mapping

import bluesky.plan_stubs as bps
from bluesky.utils import MsgGenerator

from redsun import PlanEntry


class MyController:
    def __init__(self, name: str) -> None:
        self.name = name

    def walk(
        self, motor: MyMotor, steps: int = 5, size: float = 1.0
    ) -> MsgGenerator[None]:
        for _ in range(steps):
            position = yield from bps.rd(motor.position)
            yield from bps.mv(motor.position, position + size)

    def plan_map(self) -> Mapping[str, PlanEntry]:
        return {"walk": {"plan": self.walk}}
```

Annotate every parameter with a type a plan widget can show. The list is in
[How an annotation is read](../reference/api/presenter.md#how-an-annotation-is-read),
and [How to choose the inputs of a plan](choose-plan-inputs.md) shows the
inputs a few signatures get. A device parameter takes a device class or a
runtime-checkable protocol, and the user chooses among the devices of the
session that match it.

## Run them in a presenter

The presenter owns the engine. In `setup` it asks the session for every
component that offers plans, and describes each plan with
[`create_plan_spec`][redsun.presenter.plan_spec.create_plan_spec]:

```python
from typing import Any

from psygnal import Signal

from redsun import DeviceMapping, HasPlans, slot
from redsun.engine import RunEngine
from redsun.log import Loggable
from redsun.presenter.plan_spec import (
    PlanSpec,
    UnresolvableAnnotationError,
    collect_arguments,
    create_plan_spec,
    resolve_arguments,
)


class PlanPresenter(Loggable):
    sig_finished = Signal()

    def __init__(self, name: str, *, devices: DeviceMapping) -> None:
        self.name = name
        self.devices = devices
        self.engine = RunEngine()
        self.plans: dict[str, PlanEntry] = {}
        self.specs: dict[str, PlanSpec] = {}

    def setup(self, plan_sources: Mapping[str, HasPlans]) -> None:
        for component in plan_sources.values():
            for plan, entry in component.plan_map().items():
                try:
                    self.specs[plan] = create_plan_spec(entry["plan"], self.devices)
                except (UnresolvableAnnotationError, ValueError) as error:
                    self.logger.warning(error)
                    continue
                self.plans[plan] = entry

    @slot
    def run(self, plan: str, values: dict[str, Any]) -> None:
        resolved = resolve_arguments(self.specs[plan], values, self.devices)
        args, kwargs = collect_arguments(self.specs[plan], resolved)
        future = self.engine(self.plans[plan]["plan"](*args, **kwargs))
        future.add_done_callback(lambda _: self.sig_finished.emit())
```

- The session answers `plan_sources` with every component that satisfies
  `HasPlans`, by name. See [Questions](../explanation/questions.md).
- Catching `UnresolvableAnnotationError` leaves out a plan whose parameters no
  plan widget can show, and catching `ValueError` leaves out one declaring two
  actions of one name. The other plans stay.

To run the plans with document callbacks, ask `setup` for
`callbacks: Mapping[str, CallbackType]` as well, and pass each one to
`self.engine.subscribe`.

## Show the plan widgets in a view

The view asks the same question, and builds a plan widget for each plan with
[`create_plan_widget`][redsun.view.qt.utils.create_plan_widget]:

```python
from qtpy.QtWidgets import QComboBox, QStackedWidget, QVBoxLayout, QWidget

from redsun import Placement
from redsun.qt import Dock
from redsun.view.qt.utils import PlanWidget, create_plan_widget


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

    def setup(
        self, plan_sources: Mapping[str, HasPlans], devices: DeviceMapping
    ) -> None:
        for component in plan_sources.values():
            for entry in component.plan_map().values():
                try:
                    self.add_plan(create_plan_spec(entry["plan"], devices))
                except (UnresolvableAnnotationError, ValueError):
                    continue

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
```

The combo box chooses which plan widget the stacked widget shows, and
`PlanWidget.parameters` holds the values the user chose, with each device given
by its name.

## Declare and link them

Declare the four components, and link the view's run request to the presenter
and the presenter's end-of-plan signal back to the view:

```python
from collections.abc import Iterator

from redsun import AsDevice, AsPresenter, AsView, Link
from redsun.qt import QtSession


class MyApp(QtSession):
    motor: AsDevice[MyMotor]
    ctrl: AsPresenter[MyController]
    plan_ctrl: AsPresenter[PlanPresenter]
    plan_view: AsView[PlanView]

    def wire(self) -> Iterator[Link]:
        yield self.plan_view.sig_run, self.plan_ctrl.run
        yield self.plan_ctrl.sig_finished, self.plan_view.on_finished
```

No link names `ctrl`, because the session hands it to the presenter and the
view in `setup`. Another component with a `plan_map` adds its plans to both,
with no change to either.

A plan that runs until the user stops it needs more from the presenter and the
view. See
[How to write a plan that runs until stopped](write-a-continuous-plan.md).
