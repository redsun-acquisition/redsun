---
icon: lucide/route
---

# How presenters run plans

A [plan](glossary.md#plan) is a recipe for an acquisition: a Python generator
that says, one step at a time, what to move, what to read and when. Plans come
from [`bluesky`](glossary.md#bluesky), and most of what its
[documentation on plans](https://blueskyproject.io/bluesky/main/plans.html)
says applies here too.

In `redsun`, any [component](glossary.md#component) can offer plans, and one
[presenter](glossary.md#presenter) runs them on a
[`RunEngine`](glossary.md#runengine), the object that executes plans. `redsun`
adds three things to `bluesky`:

- a `RunEngine` that runs the plan on a thread of its own and returns at once,
  where the `bluesky` one blocks the caller and freezes a window
- `PlanSpec`, a description of a plan's parameters read from its signature,
  from which a view in any [toolkit](glossary.md#toolkit) builds its controls,
  for Qt a [plan widget](glossary.md#plan-widget)
- continuous plans, which run until stopped and take actions from the user
  meanwhile, such as recording a frame on request

[How to run a plan from a presenter](../how-to/run-a-plan.md) and
[How to write a plan that runs until stopped](../how-to/write-a-continuous-plan.md)
show the code this page describes.

---

## Plans that end by themselves

The simplest plan does its steps and stops. It's an ordinary `bluesky` plan
whose parameters are annotated by [protocols](glossary.md#protocol) rather
than classes, as in
[Describing a device with a protocol](../tutorials/device-protocols.md), so it
works with any device that has what it reads and sets.

A component offers its plans through a `plan_map` method returning each under
its name as a [`PlanEntry`][redsun.PlanEntry], which makes it a
[`HasPlans`][redsun.HasPlans]. An entry can list the
[document callbacks](glossary.md#callback) the plan needs and say, with
`extendable`, whether the user may attach more. Plans stay with the component
they belong to; no central list names them.

---

## Running a session's plans

The presenter asks the session for every `HasPlans`, so a session file that
adds such a component adds its plans too, with no change to the presenter
([Questions](questions.md)). Step through a plan reaching its widget:

```d2 title="From a plan to its widget"
...@diagrams/style
grid-rows: 2
grid-columns: 2
grid-gap: 80
component: "component\nplan_map()" {
  class: step
  tooltip: Any component with a plan_map method satisfies HasPlans. It returns each plan under its name, as a PlanEntry.
}
presenter: "presenter\nholds the RunEngine" {class: hidden}
widget: "plan widget\nin a view" {class: hidden}
spec: "PlanSpec\none per plan" {class: hidden}
component -> presenter: "plans" {style.opacity: 0}
presenter -> spec: "create_plan_spec" {style.opacity: 0}
spec -> widget: "controls" {style.opacity: 0}
steps: {
  1: {
    presenter.class: step
    presenter.tooltip: In setup, the presenter asks the session for every component that satisfies HasPlans, and keeps the plans they offer.
    (component -> presenter)[0].style.opacity: 1
  }
  2: {
    spec.class: step
    spec.tooltip: create_plan_spec reads the plan's signature and type hints into a description of each parameter.
    (presenter -> spec)[0].style.opacity: 1
  }
  3: {
    widget.class: step
    widget.tooltip: The view builds one control per parameter, and a list of devices for each device parameter.
    (spec -> widget)[0].style.opacity: 1
  }
}
```

The view in [How to run a plan from a presenter](../how-to/run-a-plan.md)
asks the same question and describes each plan itself, with the session's
devices to list what can fill each device parameter. The built-in
[`AcquisitionView`][redsun.view.qt.builtins.AcquisitionView] instead takes the
presenter in `setup`, as a [`DescribesPlans`][redsun.presenter.DescribesPlans],
and reads its descriptions. They can't be a
[shared value](glossary.md#shared-value): the session reads those when it
builds a component, and the presenter describes its plans later, in `setup`.

Calling the engine returns a `Future` at once; the presenter uses it to tell
the view when the plan ended:

```d2 title="One run of a plan"
...@diagrams/style
shape: sequence_diagram
view: "view"
presenter: "presenter"
engine: "RunEngine\non its own thread"
callbacks: "document\ncallbacks"
view -> presenter: "run walk"
presenter -> engine: "the plan\nand its callbacks"
engine -> presenter: "a Future,\nat once" {style.stroke-dash: 4}
engine -> callbacks: "documents" {
  tooltip: A run emits a start document, a descriptor for each stream, events or stream documents for the data, and a stop document.
}
engine -> presenter: "Future done" {style.stroke-dash: 4}
presenter -> view: "plan ended" {
  tooltip: The view enables the controls it disabled when the plan started. The built-in AcquisitionPresenter reports a plan that raised on sig_plan_failed instead of sig_plan_done.
}
```

The callbacks a run gets are the ones its `PlanEntry` lists, then those the
user attached to it.

---

## From a plan to its widget

[`create_plan_spec`][redsun.presenter.plan_spec.create_plan_spec] makes a
`PlanSpec` from the plan's signature in plain Python, with no toolkit, so you
can inspect a plan before any application object exists.

### Plans that are refused

A plan is never shown with a control nobody can fill in. Step through three
parameters:

```d2 title="How create_plan_spec treats a parameter"
...@diagrams/style
direction: down
param: "a parameter\nof the plan" {class: step}
shown: "can a control\nshow its type?" {shape: diamond}
control: "a control in\nthe plan widget" {class: step}
default: "does it have\na default?" {shape: diamond}
hidden: "hidden: the plan\nkeeps its default" {
  class: step
  tooltip: The view leaves the parameter out. This is how the md parameter of most bluesky plans is treated.
}
refused: "UnresolvableAnnotationError" {
  class: failed
  tooltip: Any is refused on purpose, and so is a missing annotation, which reads as Any. A control for it would accept everything and show up as a bare text field.
}
param -> shown
shown -> control: "yes"
shown -> default: "no"
default -> hidden: "yes"
default -> refused: "no"
scenarios: {
  int: {
    param: "steps: int = 5" {style.stroke-width: 4}
    shown.style.stroke-width: 4
    control.style.stroke-width: 4
    default.style.opacity: 0.3
    hidden.style.opacity: 0.3
    refused.style.opacity: 0.3
  }
  md: {
    param: "md: dict[str, Any]\n| None = None" {style.stroke-width: 4}
    shown.style.stroke-width: 4
    default.style.stroke-width: 4
    hidden.style.stroke-width: 4
    control.style.opacity: 0.3
    refused.style.opacity: 0.3
  }
  anything: {
    param: "value: Any" {style.stroke-width: 4}
    shown.style.stroke-width: 4
    default.style.stroke-width: 4
    refused.style.stroke-width: 4
    control.style.opacity: 0.3
    hidden.style.opacity: 0.3
  }
}
```

It also raises `ValueError` for two actions with the same name, or a default
that breaks its own limits. A component that catches the error per plan
leaves that plan out and keeps the others, as
[`AcquisitionPresenter`][redsun.presenter.AcquisitionPresenter] does with a
warning; one that doesn't fails its whole `setup`. The
[reference](../reference/api/presenter.md#plan-specification) covers how each
annotation is read and how a widget's values become a call.

---

## Continuous plans

`@continuous` marks a plan that runs until stopped; `create_plan_spec` reads
it into `PlanSpec.continuous` and `PlanSpec.pausable`, from which the view
builds a start/stop toggle and, with `pausable=True`, a pause button. Stopping
is the normal end, so the `RunEngine` closes the stopped plan's
[run](glossary.md#run) with exit status `success`.

### In-flight actions

An action is something the user triggers while the plan runs. `PlanAction`
declares it (name, description, button labels; a frozen dataclass with no
state), and an `ActionManager`, owned by the component offering the plans,
keeps each action's state for the plans to wait on. A plan names an action as
a parameter default, such as `snap: PlanAction = SNAP`, and `create_plan_spec`
makes its button. Step through a live view that records a frame on request:

```d2 title="A continuous plan with one action"
...@diagrams/style
shape: sequence_diagram
view: "view"
plan: "plan\non the engine's thread"
actions: "ActionManager"
view -> plan: "toggle on: launch"
plan -> actions: "wait(SNAP)"
actions -> view: "snap offered"
view -> actions: "request('snap')" {style.opacity: 0}
actions -> plan: "wait returns 'snap'" {style.opacity: 0}
actions -> view: "snap running" {style.opacity: 0}
plan -> plan: "record a frame" {style.opacity: 0}
plan -> actions: "done('snap'), then wait again" {style.opacity: 0}
view -> plan: "toggle off: stop" {style.opacity: 0}
steps: {
  1: {
    (view -> actions)[0].style.opacity: 1
    (view -> actions)[0].tooltip: The view emits the request, and the presenter running the plan passes it to the ActionManager of the component that offers the plan.
  }
  2: {
    (actions -> plan)[0].style.opacity: 1
    (actions -> view)[1].style.opacity: 1
  }
  3: {
    (plan -> plan)[0].style.opacity: 1
    (plan -> actions)[1].style.opacity: 1
  }
  4: {
    (view -> plan)[1].style.opacity: 1
    (view -> plan)[1].tooltip: The presenter stops the RunEngine, which closes the run with the exit status success.
  }
}
```

`wait` returns the first action asked for, which runs until the plan calls
`done`; the others go back to idle, as all do if the plan is stopped while it
waits.

!!! warning "A stopped plan leaves its running action running"

    An action that is running when the plan is stopped stays running until
    the plan calls `done`. Call `done` in a `finally` block.

Each `wait` makes new latches, objects a plan waits on until another thread
sets them ([engine reference](../reference/api/engine.md#waiting-on-a-latch)),
so a request left over from an earlier launch can't start this one's action;
the `RunEngine` has no code for actions and only waits on those latches.
`wait` doesn't time out: it yields a [checkpoint](glossary.md#checkpoint)
every `poll_interval` seconds and does nothing else, so a plan that shows
frames while it waits needs a device that streams on its own.

The user asks through `request`, a [slot](glossary.md#slot) safe from any
thread that raises nothing; asking for an action no plan offers, or ending one
that isn't running, only logs a warning.

### Toggle actions

An action with `toggle_states` gets a button that stays pressed, showing the
first label released and the second pressed; with the default `None` it's
clicked. Releasing it sends `request(name, on=False)`, which the plan waits
for with `wait_released`.

### Following an action from a view

`ActionManager.sig_changed` reports each action's new `ActionState`, and a
connected view sets its buttons from it. Step through the three states:

```d2 title="The states of an action"
...@diagrams/style
direction: down
idle: "idle: no plan waits for it\nand none runs it\n\nthe view disables the button\nand shows a toggle released" {class: step}
offered: "offered: a plan waits for it\n\nthe view enables the button" {class: step}
running: "running: the plan took it\nand has not finished it\n\nthe view disables a clicked\nbutton; a toggle stays\nenabled, to be released" {class: step}
idle -> offered: "wait"
offered -> running: "asked for"
offered -> idle: "another was taken,\nor the plan stopped"
running -> idle: "done"
scenarios: {
  idle: {
    idle.style.stroke-width: 4
    offered.style.opacity: 0.3
    running.style.opacity: 0.3
  }
  offered: {
    offered.style.stroke-width: 4
    idle.style.opacity: 0.3
    running.style.opacity: 0.3
  }
  running: {
    running.style.stroke-width: 4
    idle.style.opacity: 0.3
    offered.style.opacity: 0.3
  }
}
```

Only the plan changes a state, so the changes arrive in the order they
happened. A request changes no state: the view that made it learns what came
of it from the next state.

---

## See also

- [How to run a plan from a presenter](../how-to/run-a-plan.md)
- [How to write a plan that runs until stopped](../how-to/write-a-continuous-plan.md)
- [How to follow a plan action from a view](../how-to/follow-a-plan-action.md)
- [`engine/actions` API](../reference/api/engine.md#actions)
- [`engine/plan_stubs` API](../reference/api/engine.md#plan-stubs)
- [`presenter/plan_spec` API](../reference/api/presenter.md#plan-specification)
- [How the Qt widgets work](qt-widgets.md#plan-widgets)
