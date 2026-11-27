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

### A presenter as a dataclass or a `pydantic` model

A presenter can also be a dataclass or a `pydantic` model, since `name` may be
anywhere in the signature:

```python
from dataclasses import dataclass
from typing import ClassVar

from psygnal import Signal
from pydantic import BaseModel


@dataclass
class DataclassController:
    name: str
    step: float = 1.0


class ModelController(BaseModel):
    name: str
    step: float = 1.0
    sig_moved: ClassVar[Signal] = Signal(str)
```

On a `pydantic` model, a signal must be a `ClassVar`, since `pydantic` refuses
a class attribute without an annotation. A value that `setup` assigns
shouldn't be a field: use `field(init=False)` on a dataclass, or a private
attribute on a model.

!!! warning "A class with `__slots__` needs `__weakref__` to own a signal"

    `psygnal` refers to the component that owns a signal weakly, so that the
    component can still be freed. A class with `__slots__` accepts no weak
    reference unless `__weakref__` is one of its slots, and `psygnal` then
    falls back to a strong reference: the component, and everything it holds,
    stays in memory until the program ends. The session refuses such a class,
    leaves it out, and logs the reason:

    ```text
    Failed to build presenter 'ctrl': MyApp.ctrl owns a signal, but
    StageController has '__slots__' without '__weakref__', so the signal would
    keep every instance alive. Add '__weakref__' to its slots, or
    'weakref_slot=True' to its dataclass decorator.
    ```

    On a class that declares its slots, add `__weakref__` to them:

    ```python
    class StageController:
        __slots__ = ("__weakref__", "name", "step")
        sig_moved = Signal(float)

        def __init__(self, name: str, *, step: float = 1.0) -> None:
            self.name = name
            self.step = step
    ```

    On a dataclass with `slots=True`, pass `weakref_slot=True` as well:

    ```python
    @dataclass(slots=True, weakref_slot=True)
    class StageController:
        name: str
        step: float = 1.0
        sig_moved: ClassVar[Signal] = Signal(float)
    ```

    A `pydantic` model needs nothing, because it already accepts weak
    references.

A Qt view can't be a `pydantic` model or a dataclass, because Qt needs its own
`QWidget.__init__` to run.

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

Declare each component on a session class, and connect the view's button to
the presenter, and the presenter back to the view, in `wire`:

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

If the file sets the same argument, `Declare` wins.

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

The device is still called `stage`. Only the key its arguments are read from
changes, which helps when that key isn't a valid Python name.

`Alias` gives the component another name:

```python
from redsun import Alias


class MyApp(QtSession):
    stage_ctrl: Annotated[AsPresenter[StagePresenter], Alias("ctrl")]
```

The alias is the name the component receives, the name the session lists it
under and the name a session file wires it by. The attribute you declared it
under still holds it, and its arguments are still read from the entry named
after that attribute, here `stage_ctrl`.

### Two of the same class

Two stages, or two copies of one plot, are normal, and each declaration makes
its own component:

```python
class MyApp(QtSession):
    stage_x: AsDevice[MyStage]
    stage_y: AsDevice[MyStage]
```

Your code reaches each one by its name, as `self.stage_x`. A component that
needs every stage, however many there are, asks the session by what they can
do: see [Questions](../explanation/questions.md).

## Describe a parameter for a form

A tool that writes [session files](../explanation/glossary.md#session-file)
for people, drawing a form for each component, learns the keys a component
takes from `redsun describe`, which reads them from its constructor. You can
give each parameter a title, a description, a unit and limits there, and
they reach the form as well:

```python
from typing import Annotated

from annotated_types import Gt
from pydantic import Field


class StagePresenter:
    def __init__(
        self,
        name: str,
        *,
        devices: DeviceMapping,
        step: Annotated[
            float,
            Gt(0),
            Field(
                title="Step",
                description="How far one press of Nudge moves the stage.",
                json_schema_extra={"unit": "um"},
            ),
        ] = 1.0,
    ) -> None: ...
```

The limit comes from `annotated-types`, as a plan's limits do, and the text
from `pydantic`'s `Field`. A unit has no key of its own in JSON Schema, so it
goes in `json_schema_extra` under `unit`. `redsun describe` then prints `step`
with all of them, and `redsun check` reports a session file giving a `step`
of 0 or less. Neither changes how the session builds the presenter: it still
passes the file's value on as it is. The
[command reference](../reference/command-line.md#describing-a-plugins-components)
shows the whole report.

## Use another component

A constructor runs before the other components exist, so you ask for another
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

To share a value, see [Share a value](share-a-value.md). To ask for "every
component that can do X", see [Questions](../explanation/questions.md).

## Clean up

Define `shutdown`, plain or `async`, and the session calls it when it shuts
down:

```python
class StagePresenter:
    def __init__(self, name: str, *, devices: DeviceMapping) -> None:
        self.name = name
        self.stage = devices["stage"]
        self.moves = open("moves.log", "a")

    def shutdown(self) -> None:
        self.moves.close()
```

The session waits up to 5 seconds for an `async` `shutdown`. If it hasn't
returned by then, the session cancels it, logs a warning naming your
component, and goes on to shut down the rest, so one device that stops
answering can't keep the program from closing.

## Test it

A component takes plain values, so a test can make it directly:

```python
from redsun.aio import run_coro


def test_nudge_moves_by_one_step() -> None:
    stage = MyStage(name="stage")
    run_coro(stage.connect(mock=True))
    ctrl = StagePresenter("ctrl", devices={"stage": stage}, step=2.0)

    run_coro(ctrl.nudge())

    assert run_coro(stage.position.get_value()) == 2.0
```

To test it inside a session without a window, declare the same components on
a plain [`Session`][redsun.Session], which makes every component and shows
nothing. Give it `mock: true`, and its devices connect as
`connect(mock=True)` does, with no service launched:

```python
from redsun import AsDevice, AsPresenter, Session


class MyHeadlessApp(Session):
    stage: AsDevice[MyStage]
    stage_ctrl: AsPresenter[StagePresenter]


def test_the_session_builds_without_hardware() -> None:
    app = MyHeadlessApp({"mock": True}).build()

    assert set(app.devices) == {"stage"}
    app.shutdown()
```
