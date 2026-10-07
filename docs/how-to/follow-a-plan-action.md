---
icon: lucide/mouse-pointer-click
---

# How to follow a plan action from a view

This guide shows how to show a button for each action of a plan, ask for the
action when the button is pressed, and set the button from what the plan
answers.
[How presenters run plans](../explanation/plans.md#following-an-action-from-a-view)
explains the states an action goes through.

## Prerequisites

You need a component that offers a plan declaring actions, and owns the
`ActionManager` the plan waits on. See
[In-flight actions](../explanation/plans.md#in-flight-actions).

## Ask, and follow the answer

The view asks with a signal carrying the name of the action and whether the
button is pressed, and follows the answer in a slot:

```python
from psygnal import Signal

from redsun import slot
from redsun.engine.actions import ActionState


class MyView(QWidget):
    sig_action_request = Signal(str, bool)

    def ask(self, name: str) -> None:
        self.sig_action_request.emit(name, True)

    def ask_or_release(self, checked: bool, name: str) -> None:
        self.sig_action_request.emit(name, checked)

    @slot
    def on_action_changed(self, name: str, state: str) -> None:
        button = self.widget.action_buttons[name]
        match state:
            case ActionState.IDLE:
                button.setEnabled(False)
                button.release()
            case ActionState.OFFERED:
                button.setEnabled(True)
            case ActionState.RUNNING:
                button.setEnabled(button.isCheckable())
```

`ask` and `ask_or_release` are the `action_clicked_callback` and
`action_toggled_callback` of the [plan widget](../explanation/qt-widgets.md#plan-widgets),
here `self.widget`. `release` shows a button released without emitting `toggled`, which unchecking
it would, and the view would then ask an action that already ended to end.

## Link the view and the component

In `wire`:

```python
class MyApp(QtSession):
    ctrl: AsPresenter[MyController]
    panel: AsView[MyView]

    def wire(self) -> Iterator[Link]:
        yield self.panel.sig_action_request, self.ctrl.actions.request
        yield self.ctrl.actions.sig_changed, self.panel.on_action_changed
```

!!! warning "The `wiring` section can't make these links"

    A path in `wiring` is `component.port`, and the ports of a component don't
    include those of an object it holds. Make the links in `wire`.

The session records an `ActionManager` under the name of the component holding
it, so it records the two links as `panel.sig_action_request -> ctrl.request`
and `ctrl.sig_changed -> panel.on_action_changed`. See
[Inspect what is connected](../how-to/wire-components.md#inspect-what-is-connected).
