---
icon: lucide/layout-panel-left
---

# How the Qt widgets of redsun work

`redsun.view.qt` gives you Qt widgets to use in the views of a session: the
controls of a plan, and a tree of a device's settings.

---

## Plan widgets

`create_plan_widget` builds a [plan widget](glossary.md#plan-widget) from a
`PlanSpec`, the description of a plan read from its signature. The widget has
an input for each parameter and a button to run the plan, and a continuous
plan also gets a toggle, a pause button and a button for each action.
`create_plan_widget` returns a `PlanWidget`, a frozen dataclass that owns the
widget tree, and its `group_box` is the page your view adds to its layout.

A plan widget runs nothing itself. When a button is pressed, it calls the view
back, and the view sends the plan's name and `PlanWidget.parameters` to the
presenter that runs the plan. As the plan starts, pauses and ends, the view
updates the widget with `toggle` and `pause`. The widget depends on no
presenter, and the `PlanSpec` it's built from depends on no toolkit.

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

A plan may require document callbacks of its own, the functions that receive
the [documents](glossary.md#document) of a run, and may let the user attach
more. `create_plan_widget` lists both in a *Callbacks* group. You pass it the
plan's own callbacks, whether the plan is extendable, and the callbacks the
user may attach, by name:

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
plan. A `Literal` or a device gets a list to choose from, a sequence of
devices gets a multiple choice, and everything else gets the `magicgui`
default.
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

```python
tree.set_value("stage-position", 12.5)  # what the device read back
tree.revert("stage-position")  # the device refused: show the value before
```

`set_value` shows the value it's given, which may differ from what was typed
when the device rounds or clips it. It also shows a value that changed with no
edit pending. Neither call emits `sig_property_changed`.

After a presenter sets the device, it reads the value back and announces it.
The view then hands the value to the tree with `set_value`, or calls `revert`
when the device refused it. Because the tree never writes to a device itself,
the value it shows is always one the device reported.

---

## See also

- [Qt widgets API reference](../reference/api/view.md#qt-widgets)
- [Plans](plans.md)
