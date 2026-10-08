---
icon: lucide/layout-panel-left
---

# How the Qt widgets work

`redsun.view.qt` gives you Qt widgets to use in the views of a session: the
controls of a plan, buttons for the actions of a running plan, and a tree of a
device's settings.

---

## Plan widgets

`create_plan_widget` builds a [plan widget](glossary.md#plan-widget) from a
`PlanSpec`, the description of a plan read from its signature. The widget has
an input for each parameter and a button to run the plan, and a continuous
plan also gets a toggle, a pause button and a button for each action.
`create_plan_widget` returns a `PlanWidget`, a frozen dataclass that owns the
widget tree, and its `group_box` is the widget your view adds to its layout.

A plan widget runs nothing itself. Step through what happens when the user
presses Run:

```d2 title="A plan widget, its view and the presenter"
...@diagrams/style
direction: down
widget: "plan widget" {class: step}
view: {class: step}
presenter: {class: step}
widget -> view: "calls back" {class: hidden}
view -> presenter: "plan name and\nPlanWidget.parameters" {class: hidden}
presenter -> view: "started, paused,\nended" {class: hidden}
view -> widget: "toggle, pause" {class: hidden}
steps: {
  1: {
    widget.class: current
    (widget -> view)[0].style.opacity: 1
  }
  2: {
    widget.class: step
    presenter: {
      class: current
      tooltip: The presenter runs the plan.
    }
    (view -> presenter)[0].style.opacity: 1
  }
  3: {
    presenter.class: step
    view.class: current
    (presenter -> view)[0].style.opacity: 1
  }
  4: {
    view.class: step
    widget.class: current
    (view -> widget)[0].style.opacity: 1
  }
}
```

The widget depends on no presenter, and the `PlanSpec` it's built from depends
on no toolkit.

Each input starts from its parameter's default and returns a value of the
annotated type. Inputs nest: a list, set, mapping, fixed-length tuple,
optional value or union gets an input built from the inputs of its parts, so a
`dict[str, list[float]]` becomes a table whose values are lists.

While an input holds a value the plan can't take, such as a repeated mapping
key or no device chosen, Run stays disabled. `PlanWidget.problems` lists the
reasons, and the first one shows under the parameters.

[How to run a plan from a presenter](../how-to/run-a-plan.md) builds the view,
and [How to write a plan that runs until stopped](../how-to/write-a-continuous-plan.md)
adds the toggle, the pause button and the action buttons.
[How to choose the inputs of a plan](../how-to/choose-plan-inputs.md) pictures
the inputs a few signatures get, and the
[reference](../reference/api/view.md#qt-widgets) lists the attributes of
`PlanWidget`.

### Document callbacks

A plan may require [document callbacks](glossary.md#callback) of its own, the
objects that receive the [documents](glossary.md#document) of a run, and may
let the user attach more. `create_plan_widget` lists both in a *Callbacks*
group. You pass it the plan's own callbacks, whether the plan is extendable,
and the callbacks the user may attach, by name:

```python
widget = create_plan_widget(
    spec,
    plan_callbacks=[median_filter],
    extendable=True,
    available_callbacks={"live_plot": live_plot, "table": table},
    attached_callbacks=["table"],
    selection_callback=on_selection,
)
widget.callbacks  # [median_filter, table]
widget.attached_callbacks  # ["table"]
```

The plan's own callbacks come first, checked and fixed in place. Each is
labelled with its name in `available_callbacks`, and one that isn't there is
labelled with its `name` attribute, or else its class name. A callback appears
once, even when it's both the plan's and available. The user can check the
others and drag them into a different order.

`callbacks` returns the checked callbacks in that order, and
`attached_callbacks` returns the names of the ones the user attached. With
`attached_callbacks=None`, every available callback starts checked, and a name
that's no longer available is ignored. A plan that carries no callback and
isn't extendable gets no group.

The widget only reports what the user selected, and it's up to the presenter
to subscribe the callbacks to the [`RunEngine`](glossary.md#runengine).

---

## Parameter widget factory

`create_param_widget` turns a `ParamDescription` into a widget from `magicgui`,
a package that builds widgets from Python types, one for each parameter of a
plan. It asks a fixed list of questions in order and builds the widget of the
first one answered yes. Pick an example parameter to follow it through:

```d2 title="How create_param_widget picks a widget"
...@diagrams/style
grid-rows: 6
grid-columns: 2
grid-gap: 40
param: "a parameter" {class: note}
gap: {class: gap}
hidden: "hidden, or does it\ncarry actions?" {class: step}
placeholder: "placeholder\nline edit" {
  class: step
  tooltip: A plan widget leaves these parameters out, so the placeholder is never shown in one.
}
many: "a sequence or set of\ndevices, or *args?" {class: step}
checks: "a list of\ncheckboxes" {
  class: step
  tooltip: One checkbox per device of the session that matches the annotation, in the Devices group of the plan widget.
}
one: "a device?" {class: step}
devices: "a combo box\nof the devices" {
  class: step
  tooltip: The devices of the session that match the annotation, in the Devices group of the plan widget.
}
choices: "a Literal?" {class: step}
literal: "a combo box\nof the choices" {class: step}
other: "anything else" {class: step}
value: "an input built\nfrom its type" {
  class: step
  tooltip: A list, set, mapping, fixed-length tuple, optional value or union gets an input built from the inputs of its parts. Anything else gets the magicgui widget for its type.
}
param -> hidden
hidden -> many: no
many -> one: no
one -> choices: no
choices -> other: no
hidden -> placeholder: yes
many -> checks: yes
one -> devices: yes
choices -> literal: yes
other -> value
scenarios: {
  device-list: {
    param.label: "detectors: Sequence[MyCamera]"
    placeholder.style.opacity: 0.3
    one.style.opacity: 0.3
    devices.style.opacity: 0.3
    choices.style.opacity: 0.3
    literal.style.opacity: 0.3
    other.style.opacity: 0.3
    value.style.opacity: 0.3
    checks.style.stroke-width: 4
  }
  device: {
    param.label: "camera: MyCamera"
    placeholder.style.opacity: 0.3
    checks.style.opacity: 0.3
    choices.style.opacity: 0.3
    literal.style.opacity: 0.3
    other.style.opacity: 0.3
    value.style.opacity: 0.3
    devices.style.stroke-width: 4
  }
  literal: {
    param.label: "mode: Literal[\"fast\", \"slow\"]"
    placeholder.style.opacity: 0.3
    checks.style.opacity: 0.3
    devices.style.opacity: 0.3
    other.style.opacity: 0.3
    value.style.opacity: 0.3
    literal.style.stroke-width: 4
  }
  other: {
    param.label: "positions: list[float]"
    placeholder.style.opacity: 0.3
    checks.style.opacity: 0.3
    devices.style.opacity: 0.3
    literal.style.opacity: 0.3
    value.style.stroke-width: 4
  }
}
```

[How an annotation is read](../reference/api/presenter.md#how-an-annotation-is-read)
lists every annotation a plan widget can show.

---

## Action buttons

`ActionButton` is a `QPushButton` that carries a `PlanAction`. An action with
`toggle_states` gets a button you can check, whose label follows the state:

```python
from redsun.view.qt.utils import ActionButton
from redsun.engine.actions import PlanAction

action = PlanAction(name="record", toggle_states=("Start", "Stop"))
btn = ActionButton(action)
# label shows "Record (Start)" when unchecked, "Record (Stop)" when checked
```

An action whose `toggle_states` is `None` gets a plain button you click, with
a label that doesn't change.

To enable and disable a button as the plan offers its action and takes it
back, see [Following an action from a view](plans.md#following-an-action-from-a-view).

---

## Descriptor tree view

`DescriptorTreeView` shows the output of a device's `describe_configuration`
and `read_configuration` as an editable tree with two columns. It shows
settings and reports edits, but it doesn't write them. A presenter does that,
through `Deferrals` while a plan runs, as
[How to change a device setting while a plan runs](../how-to/change-a-setting-while-a-plan-runs.md)
shows:

```python
from redsun.view.qt.treeview import DescriptorTreeView

tree = DescriptorTreeView(
    device.describe_configuration(),
    device.read_configuration(),
    parent=self,
)
tree.sig_property_changed.connect(on_property_changed)
```

Rows are grouped by their `name-property` key, with one header per device
name. A property whose name holds a dash of its own gets a second header under
that one, so `cam-properties-Binning` shows as `Binning` under `properties`
under `cam`. A property whose source ends in `:readonly` shows as a greyed
label.

An edit is only a request. The tree emits `sig_property_changed` and keeps the
edit pending, showing what was typed, until it's told how the request ended:

```d2 title="An edit in the tree"
...@diagrams/style
shape: sequence_diagram
tree: tree
view: view
presenter: presenter
device: device
tree -> view: "sig_property_changed,\nthe edit stays pending"
view -> presenter: "the request"
presenter -> device: "set the value"
presenter -> device: "read it back"
presenter -> view: "announce the value,\nor that the device refused it"
accepted: "if the device took it" {
  view -> tree: "set_value"
}
refused: "if the device refused it" {
  view -> tree: "revert"
}
```

```python
tree.set_value("stage-position", 12.5)  # what the device read back
tree.revert("stage-position")  # the device refused: show the value before
```

`set_value` shows the value it's given, which may differ from what was typed
when the device rounds or clips it. It also shows a value that changed with no
edit pending. Neither call emits `sig_property_changed`. Because the tree
never writes to a device itself, the value it shows is always one the device
reported.

---

## See also

- [Qt widgets API reference](../reference/api/view.md#qt-widgets)
- [Plans](plans.md)
