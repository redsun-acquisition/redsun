---
icon: lucide/loader
---

# How to show a plan's progress

A plan can report how far it has got, so that the user sees it in the plan's
[plan widget](../explanation/glossary.md#plan-widget). The plan opens a
progress scope for each thing it counts, and the plan widget shows a bar for
every scope while the plan runs.

## Prerequisites

You need a session running plans from plan widgets, as in
[Write a plan that runs until stopped](write-a-continuous-plan.md). The blocks
below are parts of that page's script, and the whole script is at the end.

## Report progress from a plan

Open a scope with `declare_progress`, move it with `update_progress`, and
finish it with `done=True`:

```{.python}
--8<-- "docs/examples/continuous_plan.py:series"
```

A scope declared with `parent` is nested under that scope, so here each series
of frames sits under the count of repeats. `current`, `initial` and `target`
are in `unit`. A plan that knows only how far it has got as a proportion passes
`fraction`, from 0 to 1, instead. A scope with no `target` has no known end.

The engine finishes every scope still open when the plan ends, however it ends,
so a plan that fails or is stopped leaves no bar behind. A plan that reports
nothing shows no bar.

## Show it in the plan widget

The engine announces every open scope on `RunEngine.sig_progress`. The
presenter that owns the engine passes the signal on through a signal of its
own:

```{.python}
--8<-- "docs/examples/continuous_plan.py:progress-relay"
```

connected in its `__init__`, once it has made the engine:

```{.python}
--8<-- "docs/examples/continuous_plan.py:progress-connect"
```

The view hands what it receives to the plan widget of the plan that is
running:

```{.python}
--8<-- "docs/examples/continuous_plan.py:progress-view"
```

and the session links the two, with
`yield self.plan_ctrl.sig_progress, self.plan_view.on_progress` in `wire`.

## Follow a device's progress

A step the plan starts without waiting, such as a move or a detector
completing, returns a status. `monitor_progress` opens a scope that follows the
status, and finishes the scope when the status is done:

```{.python}
--8<-- "docs/examples/continuous_plan.py:monitor"
```

A status that reports its progress, such as a detector's `complete` or a
motor's `set` in `ophyd-async`, fills the bar. A status that reports nothing
gets a bar with no end, which moves back and forth until the status is done.
The example's shutter is a soft signal and opens at once, so its bar is gone
almost as soon as it appears. A real shutter or motor keeps the bar in the plan
widget for as long as it moves.

The plan still waits on the status itself. A status that fails closes its
scope, and the failure reaches the plan through its `wait`. The scope belongs
to the status, so the plan doesn't update or finish it with `update_progress`.

## What a bar shows

Each scope is a row of the plan widget's "Progress" group, indented under its
parent. The plan widget hides the group while no scope is open.

| the scope has | the bar | the text |
| --- | --- | --- |
| a `target`, or a `fraction` | fills up to the end | `37 / 100 frames`, or `42 %` for a fraction |
| no end, but a `current` | moves back and forth | `412 frames` |
| nothing reported yet | moves back and forth | no text |

When the plan passes `time_remaining`, the text ends with `, 12 s left`.

## Pausing

A paused plan keeps its bars as they were, and its next `update_progress`
after it resumes moves them on.

## The example in full

??? example "The whole script"

    ```{.python}
    --8<-- "docs/examples/continuous_plan.py"
    ```
