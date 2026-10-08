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

- **A `RunEngine` that doesn't block.** The `bluesky` one blocks the thread
  that calls it until the plan ends, which freezes a window. The `redsun` one
  runs the plan on a thread of its own and returns at once.
- **`PlanSpec`**, a description of a plan's parameters read from its
  signature. It names no [toolkit](glossary.md#toolkit), so a view in any
  toolkit builds its controls from it. For Qt, those controls are a
  [plan widget](glossary.md#plan-widget).
- **Continuous plans**, which run until the user stops them and take actions
  from the user while they run, such as a live view that records a frame each
  time the user asks for one.

[How to run a plan from a presenter](../how-to/run-a-plan.md) and
[How to write a plan that runs until stopped](../how-to/write-a-continuous-plan.md)
show the code this page describes.

---

## Plans that end by themselves

The simplest plan does its steps and stops, such as a walk that reads a
stage's position and moves it forward a few times. It's an ordinary `bluesky`
plan, with parameters annotated by [protocols](glossary.md#protocol) rather
than classes, as in
[Describing a device with a protocol](../tutorials/device-protocols.md), so it
works with any device that has what it reads and sets.

A component offers its plans through a `plan_map` method, which returns each
plan under its name as a [`PlanEntry`][redsun.PlanEntry]. A component with that
method satisfies the [`HasPlans`][redsun.HasPlans] protocol. An entry may also
list the [document callbacks](glossary.md#callback) the plan needs, under
`callbacks`, and say under `extendable` whether the user may attach more. The
plans stay with the component they belong to: a component that holds a stage
offers the plans that move it, and no central list names them.

---

## Running a session's plans

The presenter that runs plans doesn't name the components that offer them. It
asks the session for every component that satisfies `HasPlans`, so a session
file that adds such a component also adds its plans, without anyone editing
the presenter. [Questions](questions.md) explains how the session answers.
Step through to see a plan reach its widget:

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

A view gets the descriptions in one of two ways. The view in
[How to run a plan from a presenter](../how-to/run-a-plan.md) asks the session
the same question as the presenter and describes each plan itself, which is
why it also asks for the session's devices: a description lists, for each
device parameter, the devices that can fill it. The built-in
[`AcquisitionView`][redsun.view.qt.builtins.AcquisitionView] takes the
presenter in its `setup` instead, as a
[`DescribesPlans`][redsun.presenter.DescribesPlans], and reads the
descriptions the presenter made. Neither can receive them as a
[shared value](glossary.md#shared-value), because the session reads shared
values when it builds a component, and the presenter only describes its plans
later, in `setup`.

Calling the engine doesn't wait for the plan to end. The call returns a
`Future`, which the presenter uses to tell the view that the plan ended, so the
view can enable the controls it disabled when the plan started:

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

A view builds a plan widget from a `PlanSpec`, which
[`create_plan_spec`][redsun.presenter.plan_spec.create_plan_spec] makes from
the plan's signature. The check is plain Python and imports no toolkit, so you
can inspect a plan before any application object exists.

### Plans that are refused

A plan is never shown with a control nobody can fill in. Step through three
parameters to see how `create_plan_spec` treats each:

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

`create_plan_spec` also raises `ValueError` for a plan that declares two
actions with the same name, since the name is what tells a plan's actions
apart, or a parameter whose default breaks its own limits.

The component that describes the plans decides what happens next. One that
catches the error for each plan leaves that plan out and keeps the others, as
[`AcquisitionPresenter`][redsun.presenter.AcquisitionPresenter] does with a
warning, while one that doesn't fails its whole `setup`.

The [reference](../reference/api/presenter.md#plan-specification) covers what
a description holds, how each annotation is read, and how the values of a plan
widget become a call.

---

## Continuous plans

The `@continuous` decorator marks a plan that runs until it's stopped. It
stores a `Continuous` on the function, which `create_plan_spec` reads into
`PlanSpec.continuous` and `PlanSpec.pausable`. The view builds the controls
from those two: a toggle to start and stop the plan, and, with
`pausable=True`, a button to pause and resume it. Stopping is the normal way
for a continuous plan to end, so the `RunEngine` closes the
[run](glossary.md#run) of a stopped plan with the exit status `success`.

### In-flight actions

An action is something the user triggers while the plan runs. Two classes
describe it:

- `PlanAction` declares it: its name, its description and the labels of its
  button. It's a frozen dataclass and holds no state.
- `ActionManager` keeps the state of each action while a plan runs. The
  component that offers the plans owns one, and the plans wait on it.

A plan names an action as the default of a parameter, such as
`snap: PlanAction = SNAP`, and `create_plan_spec` finds it there to make the
button. Step through a live view that records a frame each time the user asks:

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

`wait` offers the actions it's given, waits until one is asked for, and
returns the name of the one asked for first. That action then runs until the
plan calls `done`. The others go back to idle, as all of them do if the plan
is stopped while it waits.

!!! warning "A stopped plan leaves its running action running"

    An action that is running when the plan is stopped stays running until
    the plan calls `done`. Call `done` in a `finally` block.

Each call to `wait` makes new latches for the actions it offers. A latch is an
object a plan waits on until another thread sets it; the [engine
reference](../reference/api/engine.md#waiting-on-a-latch) describes the one
`redsun` uses. Because the latches are new each time, a request left over from
an earlier launch of the plan can't start an action of this one. The
`RunEngine` itself has no code for actions: it receives the latches `wait` made
and waits on them.

`wait` doesn't time out. While it waits, it yields a
[checkpoint](glossary.md#checkpoint) every `poll_interval` seconds, as the
[stub it uses](../reference/api/engine.md#plan-stubs) does. A plan does
nothing else while it waits, so a plan that shows frames and records one on
request needs a device that streams frames on its own.

The user asks for an action through `request`, a [slot](glossary.md#slot)
that's safe to call from any thread and raises nothing. Asking for an action
no plan offers changes nothing and is logged as a warning, and so is asking to
end an action that isn't running.

### Toggle actions

An action with `toggle_states` gets a button that stays pressed until it's
released. The first label shows while the button is released, and the second
while it's pressed. With `toggle_states=None`, the default, the button is
clicked instead.

Pressing the button asks for the action, and releasing it asks the action to
end, with `request(name, on=False)`. The plan waits for the release with
`wait_released`.

### Following an action from a view

An action is always in one of three states, and `ActionManager.sig_changed`
reports each change with the action's name and its new `ActionState`. A view
connected to it sets each button from the state it reports. Step through the
states to see what each means and what the view does:

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
