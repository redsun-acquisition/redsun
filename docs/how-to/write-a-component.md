---
icon: lucide/puzzle
---

# How to write a component

This page shows how to write each kind of
[component](../explanation/glossary.md#component) and add it to a session.
[Components](../explanation/components.md) explains the rules behind it.

## A device

Write an [`ophyd-async`](../explanation/glossary.md#ophyd-async) device. Its
constructor must accept `name` as a keyword, as every `ophyd-async` base class
does:

```python
from ophyd_async.core import StandardReadable, soft_signal_rw


class MyStage(StandardReadable):
    def __init__(self, name: str = "", *, units: str = "mm") -> None:
        with self.add_children_as_readables():
            self.position = soft_signal_rw(float, units=units)
        super().__init__(name=name)
```

Every argument after `name` can come from the session file.

## A presenter

A presenter is any class that takes `name` as a keyword and keeps it:

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

- `devices` is filled by type: [`DeviceMapping`][redsun.DeviceMapping] is
  every device of the session, by name.
- `step` comes from the session file if it is there, and is `1.0` if not.
- `nudge` is a [slot](../explanation/glossary.md#slot), so the session can
  connect a signal to it. It may be `async`.

## A view

A Qt view is a `QWidget` with a
[placement](../explanation/glossary.md#placement), and a constructor starting
with `(name: str, parent: QWidget)`:

```python
from psygnal import Signal
from qtpy.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from redsun import Placement, slot
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

## Add them to a session

```python
from collections.abc import Iterator

from redsun import AsDevice, AsPresenter, AsView, Link
from redsun.qt import QtSession


class MyApp(QtSession):
    stage: AsDevice[MyStage]
    stage_ctrl: AsPresenter[StagePresenter]
    stage_view: AsView[StageView]

    def wire(self) -> Iterator[Link]:
        yield self.stage_view.sig_nudge, self.stage_ctrl.nudge
        yield self.stage_ctrl.sig_moved, self.stage_view.show_position
```

To give a component arguments in Python rather than in the file, use
`Declare`:

```python
from typing import Annotated

from redsun import Declare


class MyApp(QtSession):
    stage_ctrl: Annotated[AsPresenter[StagePresenter], Declare(step=0.5)]
```

`Declare` wins over the file.

A component reads its arguments from the file under its own name. To read
them under another key, use `FromConfig`:

```python
from redsun import FromConfig


class MyApp(QtSession):
    stage: Annotated[AsDevice[MyStage], FromConfig("xy_stage")]
```

```yaml
devices:
  xy_stage:
    units: um
```

The device is still called `stage`. Only the key it is read from changes,
which helps when the key is not a valid Python name.

`Alias` gives the component another name:

```python
from redsun import Alias


class MyApp(QtSession):
    stage_ctrl: Annotated[AsPresenter[StagePresenter], Alias("ctrl")]
```

The name is what the component receives, what the session lists it under, and
what a session file wires it by. The attribute you declared it under still
holds it, and its arguments are still read from the entry named after that
attribute, here `stage_ctrl`.

## Use another component

A constructor runs before the other components exist, so ask for another
component, or a value it shares, in `setup`:

```python
class MotorReadings:
    """The last position read from each motor."""

    def __init__(self) -> None:
        self.positions: dict[str, float] = {}


class RoiPresenter:
    def __init__(self, name: str) -> None:
        self.name = name

    def setup(self, readings: MotorReadings) -> None:
        self.readings = readings
```

`MotorReadings` stands for any class of yours that another component shares.

See [Share a value](share-a-value.md), and [Questions](../explanation/questions.md)
to ask for "every component that can do X".

## Clean up

Define `shutdown`, plain or `async`. The session calls it when it shuts down:

```python
class StagePresenter:
    def shutdown(self) -> None:
        self._task.cancel()
```

## Test it

A component takes plain values, so a test makes it directly:

```python
from redsun.aio import run_coro


def test_nudge_moves_by_one_step() -> None:
    stage = MyStage(name="stage")
    run_coro(stage.connect(mock=True))
    ctrl = StagePresenter("ctrl", devices={"stage": stage}, step=2.0)

    run_coro(ctrl.nudge())

    assert run_coro(stage.position.get_value()) == 2.0
```

To test it inside a session without a window, build a plain
[`Session`][redsun.Session]: it makes every component and shows nothing. Give
it `mock: true` and its devices connect as `connect(mock=True)` does, with no
service launched:

```python
def test_the_session_builds_without_hardware() -> None:
    app = MyApp({"mock": True}).build()

    assert set(app.devices) == {"stage"}
    app.shutdown()
```
