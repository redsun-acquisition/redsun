---
icon: lucide/repeat
---

# How to write a plan that runs until stopped

Write a [plan](../explanation/glossary.md#plan) that loops until the user
stops it, declare actions the user can trigger while it runs, and start,
pause and stop it from its plan widget.
[Continuous plans](../explanation/plans.md#continuous-plans) explains how
actions are offered and taken.

## Prerequisites

A presenter that runs the plans of the session and a view that shows their
plan widgets, as in [How to run a plan from a presenter](run-a-plan.md). The
examples use `MyCamera`, a device that can be triggered and read and has a
`shutter` signal, through this protocol:

```python
from typing import Any, Protocol, runtime_checkable

from bluesky.protocols import Readable, Triggerable
from ophyd_async.core import SignalRW


@runtime_checkable
class Camera(Readable[Any], Triggerable, Protocol):
    shutter: SignalRW[bool]
```

## Mark the plan continuous

Decorate the plan with `continuous` and loop until it is stopped:

```python
from collections.abc import Mapping

import bluesky.plan_stubs as bps
from bluesky.utils import MsgGenerator

from redsun import PlanEntry
from redsun.engine.actions import continuous


class MyController:
    def __init__(self, name: str) -> None:
        self.name = name

    @continuous(pausable=True)
    def live(self, camera: Camera) -> MsgGenerator[None]:
        yield from bps.open_run()
        while True:
            yield from bps.checkpoint()
            yield from bps.trigger_and_read([camera])

    def plan_map(self) -> Mapping[str, PlanEntry]:
        return {"live": {"plan": self.live}}
```

The **Run** button of its plan widget becomes a toggle that starts and
stops the plan, and `pausable=True` adds a button to pause and resume it.
Stopping the plan closes the run it opened, with the exit status `success`.
The checkpoint is where the plan starts again after a pause.

## Declare actions

An action is a [`PlanAction`][redsun.engine.actions.PlanAction] given as the
default of a parameter annotated `PlanAction`. The component that offers the
plan owns an [`ActionManager`][redsun.engine.actions.ActionManager], and the
plan waits on it:

```python
from redsun.engine.actions import ActionManager, PlanAction, continuous

SNAP = PlanAction(name="snap", description="Take one frame")


class MyController:
    def __init__(self, name: str) -> None:
        self.name = name
        self.actions = ActionManager()

    ...

    @continuous
    def snapshots(self, camera: Camera, snap: PlanAction = SNAP) -> MsgGenerator[None]:
        yield from bps.open_run()
        while True:
            name = yield from self.actions.wait(snap)
            try:
                yield from bps.trigger_and_read([camera])
            finally:
                self.actions.done(name)

    def plan_map(self) -> Mapping[str, PlanEntry]:
        return {"live": {"plan": self.live}, "snapshots": {"plan": self.snapshots}}
```

`wait` returns the name of the action the user asked for, and does not time
out. Call `done` in a `finally` block, so that an action running when the
plan is stopped goes back to idle too. Give each action of a plan a name of
its own, or `create_plan_spec` raises `ValueError`.
[In-flight actions](../explanation/plans.md#in-flight-actions) describes
the states an action goes through.

The plan widget shows a button for each action.

## Add a button that stays pressed

Give the action `toggle_states`, the labels shown while the button is
released and while it is pressed. Pressing it starts the action, and
`wait_released` waits until the user releases it:

```python
SHUTTER = PlanAction(name="shutter", toggle_states=("Open", "Close"))


class MyController:
    ...

    @continuous
    def snapshots(
        self, camera: Camera, snap: PlanAction = SNAP, shutter: PlanAction = SHUTTER
    ) -> MsgGenerator[None]:
        yield from bps.open_run()
        while True:
            name = yield from self.actions.wait(snap, shutter)
            try:
                if name == snap.name:
                    yield from bps.trigger_and_read([camera])
                else:
                    yield from bps.mv(camera.shutter, True)
                    yield from self.actions.wait_released(shutter)
            finally:
                if name == shutter.name:
                    yield from bps.mv(camera.shutter, False)
                self.actions.done(name)
```

While the plan waits in `wait_released`, it offers no other action: `snap`
is disabled until the shutter is closed. A `finally` block may yield
messages, so a plan stopped with the shutter open closes it before it ends.

## Start, pause and stop it

Give the presenter that runs the plans a slot for the toggle and one for the
pause button:

```python
from concurrent.futures import Future


class PlanPresenter(Loggable):
    ...

    @slot
    def run(self, plan: str, values: dict[str, Any]) -> None:
        resolved = resolve_arguments(self.specs[plan], values, self.devices)
        args, kwargs = collect_arguments(self.specs[plan], resolved)
        future = self.engine(self.plans[plan]["plan"](*args, **kwargs))
        future.add_done_callback(self.finished)

    @slot
    def toggle(self, plan: str, on: bool, values: dict[str, Any]) -> None:
        if on:
            self.run(plan, values)
        else:
            self.engine.stop()

    @slot
    def pause(self, paused: bool) -> None:
        if paused:
            self.engine.request_pause()
        else:
            self.engine.resume().add_done_callback(self.finished)

    def finished(self, _: Future[Any]) -> None:
        if self.engine.state != "paused":
            self.sig_finished.emit()
```

Pausing ends the `Future` the engine returned, and `resume` returns a new
one. `finished` sends `sig_finished` only when the plan has ended, not when
it paused.

In the view, pass `create_plan_widget` a callback for each of the two
buttons, and update the plan widget when they are pressed:

```python
class PlanView(QWidget):
    sig_run = Signal(str, dict)
    sig_toggle = Signal(str, bool, dict)
    sig_pause = Signal(bool)

    ...

    def add_plan(self, spec: PlanSpec) -> None:
        widget = create_plan_widget(
            spec,
            run_callback=lambda: self.ask_to_run(spec.name),
            toggle_callback=lambda on: self.ask_to_toggle(spec.name, on),
            pause_callback=lambda paused: self.ask_to_pause(spec.name, paused),
            action_clicked_callback=self.ask,
            action_toggled_callback=self.ask_or_release,
        )
        self.widgets[spec.name] = widget
        self.chooser.addItem(spec.name)
        self.pages.addWidget(widget.group_box)

    def ask_to_toggle(self, plan: str, on: bool) -> None:
        self.chooser.setEnabled(not on)
        self.widgets[plan].toggle(on)
        self.sig_toggle.emit(plan, on, self.widgets[plan].parameters)

    def ask_to_pause(self, plan: str, paused: bool) -> None:
        self.widgets[plan].pause(paused)
        self.sig_pause.emit(paused)

    @slot
    def on_finished(self) -> None:
        self.setEnabled(True)
        self.chooser.setEnabled(True)
        self.widgets[self.chooser.currentText()].toggle(False)

    @slot
    def on_action_changed(self, name: str, state: str) -> None:
        for widget in self.widgets.values():
            if name in widget.action_buttons:
                self.set_action_button(widget.action_buttons[name], state)
```

`PlanWidget.toggle` sets the label of the toggle, enables the action buttons
and the pause button while the plan runs, and locks the inputs of the
parameters. Disabling the combo box keeps the user from starting a second
plan meanwhile. `on_finished` calls `toggle(False)` so that a plan that
fails or ends by itself shows as stopped. `on_action_changed` finds the
button in the plan widget that has it; `ask`, `ask_or_release` and the
`match` on the state that `set_action_button` holds are in
[How to follow a plan action from a view](follow-a-plan-action.md).

Link the view to the presenter, and to the `ActionManager` of the component
that offers the plan:

```python
class MyApp(QtSession):
    camera: AsDevice[MyCamera]
    ctrl: AsPresenter[MyController]
    plan_ctrl: AsPresenter[PlanPresenter]
    plan_view: AsView[PlanView]

    def wire(self) -> Iterator[Link]:
        yield self.plan_view.sig_run, self.plan_ctrl.run
        yield self.plan_view.sig_toggle, self.plan_ctrl.toggle
        yield self.plan_view.sig_pause, self.plan_ctrl.pause
        yield self.plan_ctrl.sig_finished, self.plan_view.on_finished
        yield self.plan_view.sig_action_request, self.ctrl.actions.request
        yield self.ctrl.actions.sig_changed, self.plan_view.on_action_changed
```
