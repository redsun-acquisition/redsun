---
icon: lucide/layout-panel-left
---

# How the Qt plan widgets work

`redsun.view.qt` provides Qt widgets for interfaces that run plans.

---

## Plan widgets

`create_plan_widget` builds a [plan widget](glossary.md#plan-widget) for a
`PlanSpec`: an input for each parameter and a button to run the plan, and for
a continuous plan a toggle, a pause button and a button for each action. It
returns a `PlanWidget`, a frozen dataclass owning the widget tree, whose
`group_box` is the page a view adds to its layout.

A plan widget runs nothing. It calls the view back when a button is pressed,
and the view sends the name of the plan and `PlanWidget.parameters` to the
presenter that runs it. The view then sets the widget as the plan starts,
pauses and ends, with `toggle` and `pause`. The widget depends on no
presenter, and the `PlanSpec` it is built from depends on no toolkit.

[How to run a plan from a presenter](../how-to/run-a-plan.md) builds the view,
and [How to write a plan that runs until stopped](../how-to/write-a-continuous-plan.md)
adds the toggle, the pause button and the action buttons. The attributes of
`PlanWidget` are in the [reference](../reference/api/view.md#qt-widgets).

### Document callbacks

A plan may require document callbacks of its own, and may let the user attach
more. Given both, and the callbacks the user may attach by name,
`create_plan_widget` lists them in a *Callbacks* group:

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
labelled with the name it has in `available_callbacks`, and listed once, or
with its `name` attribute or class name when it is not there. The others can be
checked and dragged into a different order. `callbacks` returns the checked
callbacks in that order, and `attached_callbacks` the names of the ones the
user attached. `attached_callbacks=None` checks every available callback, and a
name that is no longer available is ignored. A plan that carries no callback
and is not extendable gets no group.

The widget only reports the selection. Subscribing the callbacks to the run
engine is left to the presenter.

---

## Parameter widget factory

`create_param_widget` maps a `ParamDescription` to a `magicgui` widget:

| Annotation | Widget |
|-----------|--------|
| `Literal["a", "b"]` | `ComboBox` |
| `MyDevice` (single) | `ComboBox` |
| `Sequence[MyDevice]` | `Select` (multi-select) |
| `Sequence[T]` (non-device) | `ListEdit` |
| `Path` | `FileEdit` |
| `int`, `float`, `str`, ... | `create_widget` (`magicgui` default) |

---

## Action buttons

`ActionButton` is a `QPushButton` carrying a `PlanAction`. An action with
`toggle_states` gets a button that can be checked, and whose label follows the
state:

```python
from redsun.view.qt.utils import ActionButton
from redsun.engine.actions import PlanAction

action = PlanAction(name="record", toggle_states=("Start", "Stop"))
btn = ActionButton(action)
# label shows "Record (Start)" when unchecked, "Record (Stop)" when checked
```

An action whose `toggle_states` is `None` gets a button that is clicked, and
whose label does not change.

To enable and disable a button as the plan offers and takes its action, see
[Following an action from a view](plans.md#following-an-action-from-a-view).

---

## Descriptor tree view

`DescriptorTreeView` renders a device's `describe_configuration` /
`read_configuration` output as an editable two-column tree:

```python
from redsun.view.qt.treeview import DescriptorTreeView

tree = DescriptorTreeView(
    device.describe_configuration(),
    device.read_configuration(),
    parent=self,
)
tree.sig_property_changed.connect(on_property_changed)
```

Rows are grouped by their `name-property` key: one header per device name,
and a header under it for a property naming a group with a dash of its own,
so `cam-properties-Binning` is `Binning` under `properties` under `cam`. A
property whose source ends in `:readonly` is shown as a greyed label.

An edit is a request. The tree emits `sig_property_changed` and keeps the
edit pending, showing what was typed, until it is told what came of it:

```python
tree.set_value("stage-position", 12.5)  # what the device read back
tree.revert("stage-position")  # the device refused: show the value before
```

`set_value` shows the value given, which may differ from the one typed when
the device rounds or clips it. It also shows a value that changed with no
edit pending. Neither call emits `sig_property_changed`.

A presenter setting the device announces the value it reads back afterwards,
and the view hands it to the tree:

```python
class MyController:
    sig_new_configuration = Signal(str, object)
    sig_refused = Signal(str)

    @slot
    async def set(self, device: str, property: str, value: object) -> None:
        signal = self.settings[device][property]
        try:
            await signal.set(value)
        except Exception:
            self.sig_refused.emit(signal.name)
            return
        reading = await signal.read()
        self.sig_new_configuration.emit(signal.name, reading[signal.name]["value"])


class MyView(QWidget):
    @slot
    def on_new_configuration(self, key: str, value: object) -> None:
        self.tree.set_value(key, value)

    @slot
    def on_refused(self, key: str) -> None:
        self.tree.revert(key)
```

---

## See also

- [Qt widgets API reference](../reference/api/view.md#qt-widgets)
- [Plans](plans.md)
