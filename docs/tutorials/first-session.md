# Your first session

In this tutorial you build a small application: a simulated motor stage, a
button that moves it, and a label that shows where it is. It takes about
fifteen minutes, and needs no hardware.

You will write the three kinds of
[component](../reference/glossary.md#component), put them in a
[session](../reference/glossary.md#session), and connect them.

## Before you start

Install `redsun` with a Qt binding:

```bash
pip install "redsun[pyqt]"
```

Make an empty file called `first_session.py`. Everything below goes in it.

## 1. The device

A [device](../reference/glossary.md#device) talks to hardware. You have no
hardware, so this one keeps its position in memory, using a "soft" signal from
`ophyd-async`:

```python
from ophyd_async.core import StandardReadable, soft_signal_rw


class MyStage(StandardReadable):
    def __init__(self, name: str = "", *, units: str = "mm") -> None:
        with self.add_children_as_readables():
            self.position = soft_signal_rw(float, units=units)
        super().__init__(name=name)
```

A real stage would replace `soft_signal_rw` with signals that reach the
hardware. Nothing else in this tutorial would change.

## 2. The presenter

A [presenter](../reference/glossary.md#presenter) holds the behaviour. This
one moves the stage by one step, and announces where it went:

```python
from psygnal import Signal

from redsun import DeviceMapping, slot


class StagePresenter:
    sig_moved = Signal(float)

    def __init__(self, name: str, *, devices: DeviceMapping, step: float = 1.0) -> None:
        self.name = name
        self.stage = devices["stage"]
        self.step = step

    @slot
    async def nudge(self) -> None:
        position = await self.stage.position.get_value()
        await self.stage.position.set(position + self.step)
        self.sig_moved.emit(position + self.step)
```

Look at the constructor. You never call it yourself: the session does. It
passes the component's `name`, and finds a value for every other parameter:

- `devices` has the type `DeviceMapping`, so the session passes all its
  devices, by name.
- `step` has a default, so it is `1.0` unless you say otherwise.

`sig_moved` is a [signal](../reference/glossary.md#signal): the presenter
sends it, and does not care who listens. `nudge` is a
[slot](../reference/glossary.md#slot): something another component can
trigger.

## 3. The view

A [view](../reference/glossary.md#view) is what the user sees. This one is a
button and a label:

```python
from qtpy.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from redsun import Placement
from redsun.qt import Dock


class StageView(QWidget):
    placement: Placement = Dock("left")
    sig_nudge = Signal()

    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.name = name
        button = QPushButton("Nudge")
        button.clicked.connect(self.sig_nudge.emit)
        self.label = QLabel("position: 0.0")
        layout = QVBoxLayout(self)
        layout.addWidget(button)
        layout.addWidget(self.label)

    @slot
    def show_position(self, position: float) -> None:
        self.label.setText(f"position: {position}")
```

`placement` says where the view goes: docked on the left of the window. The
constructor takes `name` and `parent`, which every Qt view must.

Notice that the view knows nothing about the presenter, and the presenter
knows nothing about the view. Each only has signals and slots.

## 4. The session

Now put the three together:

```python
from redsun import AsDevice, AsPresenter, AsView
from redsun.qt import QtSession


class FirstSession(QtSession):
    stage: AsDevice[MyStage]
    stage_ctrl: AsPresenter[StagePresenter]
    stage_view: AsView[StageView]

    def wire(self) -> None:
        self.connect(self.stage_view.sig_nudge, self.stage_ctrl.nudge)
        self.connect(self.stage_ctrl.sig_moved, self.stage_view.show_position)


if __name__ == "__main__":
    FirstSession().run()
```

Each line in the class body is a component. The name on the left, `stage`, is
the component's name; that is why the presenter finds it as
`devices["stage"]`. The part on the right says its
[layer](../reference/glossary.md#layer) and its class.

`wire` connects the pieces: pressing the button nudges the stage, and the
stage's new position reaches the label.

## 5. Run it

```bash
python first_session.py
```

A window opens with the button on the left. Press it: the label counts up by
one each time.

## 6. Change a setting without touching the code

Make a file called `session.yaml` beside the script:

```yaml
session: first-session

presenters:
  stage_ctrl:
    step: 0.5
```

Tell the session to read it, by adding one line to the class:

```python
class FirstSession(QtSession):
    config = "session.yaml"
    ...
```

Run it again. Each press now moves the stage by `0.5`: the session found
`step` in the file and passed it to the presenter's constructor.

## What you learned

- A device talks to hardware, a presenter holds the behaviour, a view shows
  it.
- Components never create each other. The session makes them, and fills
  their constructors by name, by type, or from the session file.
- Components talk through signals and slots, and the session decides who is
  connected to whom.

## Next steps

- [Write a component](../how-to/write-a-component.md) has more detail on each
  kind.
- [Sessions](../explanation/session.md) explains what happens when a session
  builds.
- [Write a session file](../how-to/write-a-session-file.md) lists everything
  a file can say.
