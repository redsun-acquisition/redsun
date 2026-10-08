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
`PlanSpec`: an input per parameter and a Run button, plus, for a continuous
plan, a toggle, a pause button and a button per action. It returns a
`PlanWidget`, a frozen dataclass owning the widget tree, whose `group_box`
your view adds to its layout. The widget runs nothing itself; step through
what happens when the user presses Run:

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

Each input starts from its default and returns a value of the annotated type.
Inputs nest, so a `dict[str, list[float]]` becomes a table whose values are
lists. While an input holds a value the plan can't take, such as a repeated
key or no device chosen, Run stays disabled and the first of
`PlanWidget.problems` shows under the parameters.
[How to run a plan from a presenter](../how-to/run-a-plan.md),
[How to write a plan that runs until stopped](../how-to/write-a-continuous-plan.md)
and [How to choose the inputs of a plan](../how-to/choose-plan-inputs.md)
show them in use.

### Document callbacks

A plan's own [document callbacks](glossary.md#callback), which receive a
run's [documents](glossary.md#document), and those the user may attach are
listed in a *Callbacks* group:

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

The plan's own callbacks come first, checked and fixed; each shows its name
in `available_callbacks`, else its `name` attribute or class name, and appears
once even when also available. The user checks and reorders the others.
`callbacks` returns the checked ones in order and `attached_callbacks` the
names the user attached; with `attached_callbacks=None` every available one
starts checked, and a name no longer available is ignored. A plan with no
callback that isn't extendable gets no group. The widget only reports the
choice; the presenter subscribes the callbacks to the
[`RunEngine`](glossary.md#runengine).

---

## Parameter widget factory

`create_param_widget` turns each parameter's `ParamDescription` into a widget
from `magicgui`, a package that builds widgets from Python types, by asking
fixed questions in order. Pick an example parameter to follow it through:

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

`DescriptorTreeView` shows a device's `describe_configuration` and
`read_configuration` as an editable two-column tree. It reports edits but
writes nothing; a presenter does, through `Deferrals` while a plan runs
([How to change a device setting while a plan runs](../how-to/change-a-setting-while-a-plan-runs.md)):

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
when the device rounds or clips it, and neither call emits
`sig_property_changed`, so the tree only ever shows values the device
reported.

---

## See also

- [Qt widgets API reference](../reference/api/view.md#qt-widgets)
- [Plans](plans.md)
