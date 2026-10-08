---
icon: lucide/repeat
---

# How to write a plan that runs until stopped

Here you write a [plan](../explanation/glossary.md#plan) that loops until the
user stops it, declare actions the user can trigger while it runs, and start,
pause and stop it from its plan widget.
[Continuous plans](../explanation/plans.md#continuous-plans) explains how
actions are offered and taken.

## Prerequisites

You need a presenter that runs the plans of the session and a view that shows
their plan widgets, as in [How to run a plan from a presenter](run-a-plan.md).
This guide adds to both. The blocks below are parts of one script, and the
whole script is at the end. The text before each block names the class it
belongs to.

The plans take a camera that can be triggered and read and has a `shutter`
signal, through this protocol:

```{.python}
--8<-- "docs/examples/continuous_plan.py:protocol"
```

## Mark the plan continuous

In the component that offers the plan, decorate it with `continuous` and loop
until it is stopped. In `MyController`:

```{.python}
--8<-- "docs/examples/continuous_plan.py:live"
```

The **Run** button of its plan widget becomes a toggle that starts and stops
the plan, and `pausable=True` adds a button to pause and resume it. After a
pause, the plan starts again from the checkpoint.

## Declare actions

You declare an action as a [`PlanAction`][redsun.engine.actions.PlanAction]
given as the default of a parameter annotated `PlanAction`:

```{.python}
--8<-- "docs/examples/continuous_plan.py:actions"
```

A `PlanAction` with `toggle_states` gets a button that stays pressed. The
states are the labels shown while the button is released and while it is
pressed.

The component that offers the plan owns an
[`ActionManager`][redsun.engine.actions.ActionManager] in `self.actions`, and
the plan waits on it. In `MyController`:

```{.python}
--8<-- "docs/examples/continuous_plan.py:snapshots"
```

`wait` returns the name of the action the user asked for, and doesn't time
out. `wait_released` waits until the user releases a toggle button. Call `done`
in a `finally` block, so that an action running when the plan is stopped goes
back to idle too. A `finally` block may yield messages, so a plan stopped with
the shutter open closes it.

!!! warning "Two actions with one name raise"

    `create_plan_spec` raises `ValueError` when a plan declares two actions of
    the same name. Give each action of a plan a name of its own.

## Start, pause and stop it

In `PlanPresenter`, keep the futures of the plan that runs, add a slot for
the toggle and one for the pause button, and stop the plan at shutdown:

```{.python}
--8<-- "docs/examples/continuous_plan.py:presenter-slots"
```

The engine returns a `Future` for each plan it starts, and `watch` keeps it in
`self.futures`, an empty set made in `__init__`, until it completes. Step
through what each button does to the engine and to the futures kept:

```d2 title="Start, pause and stop a continuous plan"
...@diagrams/style
direction: down
idle: "idle\nno Future kept" {
  class: step
  tooltip: run refuses a second plan while a Future is kept, so a plan starts only from here.
}
running: "running\nits Future kept" {class: hidden}
paused: "paused\nno Future kept" {class: hidden}
finished: "sig_finished\nsent once" {class: hidden}
idle -> running: "toggle on: run()" {style.opacity: 0}
running -> paused: "Pause: request_pause(defer=True)" {style.opacity: 0}
paused -> running: "Resume: resume()" {style.opacity: 0}
running -> finished: "toggle off: stop(),\nor the plan ends or fails" {
  style.opacity: 0
}
paused -> finished: "toggle off: stop()" {style.opacity: 0}
steps: {
  1: {
    running.class: current
    running.tooltip: The engine runs the plan and watch keeps the Future it returned.
    (idle -> running)[0].style.opacity: 1
  }
  2: {
    running.class: step
    paused.class: current
    paused.tooltip: The plan pauses at its next checkpoint. Its Future completes with a RunEngineInterrupted exception, and the engine stays in the state paused, so finished sends nothing.
    (running -> paused)[0].style.opacity: 1
  }
  3: {
    paused.class: step
    running.class: current
    running.tooltip: resume returns a new Future, which watch keeps. The plan starts again from the checkpoint.
    (paused -> running)[0].style.opacity: 1
  }
  4: {
    running.class: step
    finished.class: current
    finished.tooltip: stop returns a Future that completes once the plan has cleaned up. The stop button stays enabled while the plan is paused, so you stop a paused plan the same way. finished sends sig_finished when the last Future kept is complete and the engine is not paused, so once for each plan.
    (running -> finished)[0].style.opacity: 1
    (paused -> finished)[0].style.opacity: 1
  }
}
```

`request_pause` comes from `bluesky` without type annotations, so
`mypy --strict` reports it as `no-untyped-call`.

In `PlanView`, pass `create_plan_widget` a callback for each button, and
update the plan widget when they are pressed and when the plan ends:

```{.python}
--8<-- "docs/examples/continuous_plan.py:view-controls"
```

`PlanWidget.toggle` sets the label of the toggle, enables the action buttons
and the pause button while the plan runs, and locks the inputs of the
parameters. `on_finished` calls `toggle(False)` so that a plan that fails or
ends by itself shows as stopped. Disabling the combo box keeps the user from
starting a second plan meanwhile.

## Follow the actions

In `PlanView`, ask for an action when its button is pressed, and set each
button from the state the `ActionManager` reports:

```{.python}
--8<-- "docs/examples/continuous_plan.py:view-actions"
```

[How to follow a plan action from a view](follow-a-plan-action.md) explains the
three states and why the view calls `release`.

## Link them

Link the view to the presenter, and to the `ActionManager` of the component
that offers the plan:

```{.python}
--8<-- "docs/examples/continuous_plan.py:session"
```

## The example in full

??? example "The whole script"

    ```{.python}
    --8<-- "docs/examples/continuous_plan.py"
    ```
