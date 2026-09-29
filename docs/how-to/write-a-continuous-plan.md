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
plan widgets, as in [How to run a plan from a presenter](run-a-plan.md). This
guide adds to both. The blocks below are parts of one script; the whole
script is at the end, and the text before each block names the class it
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

The **Run** button of its plan widget becomes a toggle that starts and
stops the plan, and `pausable=True` adds a button to pause and resume it.
The checkpoint is where the plan starts again after a pause.

## Declare actions

An action is a [`PlanAction`][redsun.engine.actions.PlanAction] given as the
default of a parameter annotated `PlanAction`:

```{.python}
--8<-- "docs/examples/continuous_plan.py:actions"
```

A `PlanAction` with `toggle_states` gets a button that stays pressed, with
the labels shown while it is released and while it is pressed.

The component that offers the plan owns an
[`ActionManager`][redsun.engine.actions.ActionManager] in `self.actions`, and
the plan waits on it. In `MyController`:

```{.python}
--8<-- "docs/examples/continuous_plan.py:snapshots"
```

`wait` returns the name of the action the user asked for, and does not time
out. `wait_released` waits until the user releases a toggle button. Call
`done` in a `finally` block, so that an action running when the plan is
stopped goes back to idle too; a `finally` block may yield messages, so a
plan stopped with the shutter open closes it. Give each action of a plan a
name of its own, or `create_plan_spec` raises `ValueError`.

## Start, pause and stop it

In `PlanPresenter`, keep the futures of the plan that runs, add a slot for
the toggle and one for the pause button, and stop the plan at shutdown:

```{.python}
--8<-- "docs/examples/continuous_plan.py:presenter-slots"
```

- The engine returns a `Future` for each plan it starts. `watch` keeps it in
  `self.futures`, an empty set made in `__init__`, until it completes, and
  `run` refuses a second plan while one is kept.
- `request_pause(defer=True)` pauses at the next checkpoint of the plan.
  Pausing completes the `Future` with a `RunEngineInterrupted` exception,
  and the engine stays in the state `paused`. `resume` returns a new `Future`, which `watch` keeps.
- `stop` also returns a `Future`, which completes once the plan has cleaned
  up. `finished` sends `sig_finished` when the last `Future` kept is
  complete and the engine is not paused, so once for each plan.
- `request_pause` comes from `bluesky` without type annotations, so
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

[How to follow a plan action from a view](follow-a-plan-action.md) explains
the three states and why `release` is used.

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
