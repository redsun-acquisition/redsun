# Qt widgets

`redsun.view.qt` provides reusable Qt widgets for building plan-driven UIs.

---

## Plan widgets

`create_plan_widget` builds a complete parameter form for a `PlanSpec`:

```python
from redsun.view.qt.utils import create_plan_widget

widget = create_plan_widget(
    spec,
    run_callback=on_run,
    toggle_callback=on_toggle,
    pause_callback=on_pause,
    action_clicked_callback=on_action,
    action_toggled_callback=on_action_toggled,
)
stack.addWidget(widget.group_box)
```

The returned `PlanWidget` is a frozen dataclass that owns the full widget tree:

| Attribute | Type | Description |
|-----------|------|-------------|
| `group_box` | `QWidget` | top-level page for a `QStackedWidget` |
| `container` | `mgw.Container` | magicgui parameter form |
| `run_button` | `QPushButton` | run / stop button |
| `pause_button` | `QPushButton \| None` | pause / resume (pausable plans only) |
| `actions_group` | `QGroupBox \| None` | action buttons (if any) |
| `action_buttons` | `dict[str, ActionButton]` | per-action button access |
| `callbacks_list` | `QListWidget \| None` | document callbacks to run the plan with (if any) |

### Runtime control

The presenter drives UI state through `PlanWidget`'s methods:

```python
widget.toggle(True)  # plan started  -> "Stop", enables actions
widget.toggle(False)  # plan stopped  -> "Run", disables actions
widget.pause(True)  # paused        -> "Resume", disables run button
widget.pause(False)  # resumed       -> "Pause", enables run button
widget.setEnabled(False)  # disable whole widget during setup
widget.enable_actions(True)  # enable action buttons independently
```

### Reading parameter values

```python
args, kwargs = collect_arguments(spec, widget.parameters)
```

`widget.parameters` returns `{name: value}` for every widget in the container.

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

`create_param_widget` maps a `ParamDescription` to a magicgui widget:

| Annotation | Widget |
|-----------|--------|
| `Literal["a", "b"]` | `ComboBox` |
| `MyDevice` (single) | `ComboBox` |
| `Sequence[MyDevice]` | `Select` (multi-select) |
| `Sequence[T]` (non-device) | `ListEdit` |
| `Path` | `FileEdit` |
| `int`, `float`, `str`, ... | `create_widget` (magicgui default) |

---

## Action buttons

`ActionButton` is a `QPushButton` that carries `Action` metadata. For togglable
actions it auto-updates its label based on the toggle state:

```python
from redsun.view.qt.utils import ActionButton
from redsun.engine.actions import Action

action = Action(name="led", togglable=True, toggle_states=("On", "Off"))
btn = ActionButton(action)
# label shows "Led (On)" when checked, "Led (Off)" when unchecked
```

---

## Descriptor tree view

`DescriptorTreeView` renders a device's `describe_configuration` /
`read_configuration` output as an editable two-column property tree:

```python
from redsun.view.qt.treeview import DescriptorTreeView

tree = DescriptorTreeView(
    device.describe_configuration(),
    device.read_configuration(),
    parent=self,
)
tree.sig_property_changed.connect(on_property_changed)
```

The view groups properties by their `source` field. Properties whose source
carries a `:readonly` suffix are rendered as greyed labels.

To push a live value update:

```python
tree.update_reading("stage-position", new_reading)
```

To confirm or revert a pending edit:

```python
tree.confirm_change("stage-position", success=True)  # keep new value
tree.confirm_change("stage-position", success=False)  # revert
```

---

## See also

- [Qt widgets API reference](../../reference/api/view.md#qt-widgets)
- [Plans](plans.md)
