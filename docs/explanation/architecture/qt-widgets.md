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

### Runtime control

The presenter drives UI state through `PlanWidget`'s methods:

```python
widget.toggle(True)          # plan started  → "Stop", enables actions
widget.toggle(False)         # plan stopped  → "Run", disables actions
widget.pause(True)           # paused        → "Resume", disables run button
widget.pause(False)          # resumed       → "Pause", enables run button
widget.setEnabled(False)     # disable whole widget during setup
widget.enable_actions(True)  # enable action buttons independently
```

### Reading parameter values

```python
args, kwargs = collect_arguments(spec, widget.parameters)
```

`widget.parameters` returns `{name: value}` for every widget in the container.

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
| `int`, `float`, `str`, … | `create_widget` (magicgui default) |

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
tree.sigPropertyChanged.connect(on_property_changed)
```

The view groups properties by their `source` field. Properties whose source
carries a `:readonly` suffix are rendered as greyed labels.

To push a live value update:

```python
tree.update_reading("stage-position", new_reading)
```

To confirm or revert a pending edit:

```python
tree.confirm_change("stage-position", success=True)   # keep new value
tree.confirm_change("stage-position", success=False)  # revert
```

---

## See also

- [Qt widgets API reference](../../reference/api/view.md#qt-widgets)
- [Plans](plans.md)
