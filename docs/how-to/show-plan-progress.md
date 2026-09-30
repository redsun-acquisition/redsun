---
icon: lucide/loader
---

# How to show a plan's progress

Report from a plan how far it has got, and show it on the plan's page. A
plan opens a progress scope for each thing it counts, and the page shows a
bar for every scope while the plan runs.

## Prerequisites

A session running plans from plan widgets, as in
[Write a plan that runs until stopped](write-a-continuous-plan.md). The
blocks below are parts of that page's script; the whole script is at the
end.

## Report progress from a plan

Open a scope with `declare_progress`, move it with `update_progress`, and
finish it with `done=True`:

```{.python}
--8<-- "docs/examples/continuous_plan.py:series"
```

A scope declared with `parent` is nested under that scope: here each series
of frames sits under the count of repeats. `current`, `initial` and `target`
are in `unit`; a plan that knows only how far it has got as a proportion
passes `fraction`, from 0 to 1, instead. A scope with no `target` has no
known end.

The engine finishes every scope still open when the plan ends, however it
ends, so a plan that fails or is stopped leaves no bar behind. A plan that
reports nothing shows no bar.

## Show it on the page

The engine announces every open scope on `RunEngine.sig_progress`. The
presenter owning the engine passes the signal on through a signal of its
own:

```{.python}
--8<-- "docs/examples/continuous_plan.py:progress-relay"
```

connected in its `__init__`, once it has made the engine:

```{.python}
--8<-- "docs/examples/continuous_plan.py:progress-connect"
```

The view hands what it receives to the page of the plan that is running:

```{.python}
--8<-- "docs/examples/continuous_plan.py:progress-view"
```

and the session links the two, with
`yield self.plan_ctrl.sig_progress, self.plan_view.on_progress` in `wire`.

## Follow a device's progress

A step the plan starts without waiting, such as a move or a detector
completing, returns a status. `monitor_progress` opens a scope that follows
it, and finishes the scope when the status is done:

```{.python}
--8<-- "docs/examples/continuous_plan.py:monitor"
```

A status that reports its progress, such as a detector's `complete` or a
motor's `set` in `ophyd-async`, fills the bar. The shutter's status here
reports nothing, so its bar has no end and moves back and forth until the
shutter is open. The plan still waits on the status itself: a status that
fails closes its scope, and the failure reaches the plan through its `wait`.

## What a bar shows

Each scope is a row of the page's "Progress" group, indented under its
parent. The group is hidden while no scope is open.

| the scope has | the bar | the text |
| --- | --- | --- |
| a `target`, or a `fraction` | fills up to the end | `37 / 100 frames`, or `42 %` for a fraction |
| no end, but a `current` | moves back and forth | `412 frames` |
| nothing reported yet | moves back and forth | no text |

When the plan passes `time_remaining`, the text ends with `, 12 s left`.

## Pausing

A paused plan keeps its bars as they were. When it resumes, its next
`update_progress` moves them on.

## The example in full

??? example "The whole script"

    ```{.python}
    --8<-- "docs/examples/continuous_plan.py"
    ```
