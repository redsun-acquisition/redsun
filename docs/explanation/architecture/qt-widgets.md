# Qt widgets

`redsun.view.qt` provides Qt widgets for interfaces that run plans.

---

## Plan widgets

`create_plan_widget` builds a parameter form for a `PlanSpec`:

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

It returns a `PlanWidget`, a frozen dataclass owning the widget tree:

| Attribute | Type | Description |
|-----------|------|-------------|
| `group_box` | `QWidget` | top-level page for a `QStackedWidget` |
| `container` | `mgw.Container` | `magicgui` parameter form |
| `run_button` | `QPushButton` | run / stop button |
| `pause_button` | `QPushButton \| None` | pause / resume (pausable plans only) |
| `actions_group` | `QGroupBox \| None` | action buttons (if any) |
| `action_buttons` | `dict[str, ActionButton]` | per-action button access |

### Runtime control

The presenter sets the widget's state through its methods:

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

`widget.parameters` returns `{name: value}` for every widget in the form.

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

`ActionButton` is a `QPushButton` carrying an `Action`. For a togglable action
its label follows the toggle state:

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

Properties are grouped by their `source` field. A property whose source ends
in `:readonly` is shown as a greyed label.

Update a value:

```python
tree.update_reading("stage-position", new_reading)
```

Confirm or revert a pending edit:

```python
tree.confirm_change("stage-position", success=True)  # keep new value
tree.confirm_change("stage-position", success=False)  # revert
```

---

## See also

- [Qt widgets API reference](../../reference/api/view.md#qt-widgets)
- [Plans](plans.md)
