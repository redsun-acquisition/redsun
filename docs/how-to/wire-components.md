---
icon: lucide/cable
---

# How to wire components together

Components don't connect themselves. A presenter declares
[signals](../explanation/glossary.md#signal), a view declares signals and
[slots](../explanation/glossary.md#slot), and the
[session](../explanation/glossary.md#session) says which signal reaches which
slot.

You can write the connections in the session class or in the session file, and
each example below shows both. Picking a tab switches every tab on the site to
the same form.

=== "Session class"

    Override [`wire`][redsun.Session.wire] and yield each link.

=== "Session file"

    List the connections in the `wiring` section.

## Mark a method as a slot

Decorate a method with [`slot`][redsun.slot] to let the session connect to it.
Only marked methods can be connected. Once a method is marked, other code
relies on its name and arguments, so treat them as public.

```python
from typing import Any

from bluesky.protocols import Reading
from qtpy.QtWidgets import QWidget

from redsun import slot


class ImageView(QWidget):
    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.name = name
        self.images: dict[str, Any] = {}

    @slot
    def update_layers(self, readings: dict[str, Reading[Any]]) -> None:
        for key, reading in readings.items():
            self.images[key] = reading["value"]
```

`slot` takes three options:

```python
    @slot(name="frames", thread="current")
    def update_layers(self, readings: dict[str, Reading[Any]]) -> None: ...
```

- `name` is the port name a session file uses. It defaults to the method name
  without leading underscores, so you can rename the method without breaking a
  file.
- `thread` chooses the thread the slot runs on: `"main"` for the main thread,
  `"current"` for the thread that made the connection, which is the one the
  session was built on, or a `threading.Thread`. Left out, the session
  chooses, as
  [Choose the thread a slot runs on](#choose-the-thread-a-slot-runs-on)
  describes.
- `signal` names the signals a [pairing](#pair-two-components) connects to
  the slot.

Signals need no marker: every public [`Signal`][psygnal.Signal] attribute is a
[port](../explanation/glossary.md#port):

```python
from psygnal import Signal


class DetectorPresenter:
    sig_new_data = Signal(dict)

    def __init__(self, name: str) -> None:
        self.name = name

    @slot
    def configure(self, settings: dict[str, Any]) -> None: ...
```

The examples below connect this presenter to the view above, and to a
`DetectorView` that sends `sig_property_changed`.

## Declare the connections

=== "Session class"

    Every component exists when `wire` runs, under the attribute it was declared
    as. `wire` is a generator, so you yield a signal and the slot it reaches,
    one pair per link.

    ```python
    from collections.abc import Iterator

    from redsun import AsPresenter, AsView, Link
    from redsun.qt import QtSession


    class MyApp(QtSession):
        det_ctrl: AsPresenter[DetectorPresenter]
        img_widget: AsView[ImageView]
        det_widget: AsView[DetectorView]

        def wire(self) -> Iterator[Link]:
            yield self.det_ctrl.sig_new_data, self.img_widget.update_layers
            yield self.det_widget.sig_property_changed, self.det_ctrl.configure
    ```

    Each attribute has the type it was declared with, so a misspelled signal is a
    type error before the program runs. If `wire` is an ordinary method with no
    `yield`, it returns `None` and the session raises
    [`WiringError`][redsun.WiringError].

=== "Session file"

    Each signal maps to one slot, or a list of slots, both written
    `component.port`:

    ```yaml
    session: my-lab
    frontend: qt

    presenters:
      det_ctrl:
        plugin_name: my-plugin
        plugin_id: detector

    views:
      img_widget:
        plugin_name: my-plugin
        plugin_id: image
      det_widget:
        plugin_name: my-plugin
        plugin_id: detector-view

    wiring:
      det_ctrl.sig_new_data: img_widget.update_layers
      det_widget.sig_property_changed: det_ctrl.configure
    ```

    A signal's port is its attribute name, and a slot's port is the name the
    slot declares.

A session may use both, and `wire` runs first, then the `wiring` section. You
can wire the [path provider](../explanation/glossary.md#path-provider) too, as
`path_provider`.

!!! warning "Calling and connecting for one action can run it twice"

    A component can reach another in two ways: it can ask for it in `setup`
    and call its methods, or it can send a signal that the session connects
    to one of its slots. This view uses both for one action, so each click
    moves the stage twice. Use one way for one action:

    ```python
    class StageView(QWidget):
        sig_nudge = Signal()

        def setup(self, ctrl: StagePresenter) -> None:
            self.ctrl = ctrl

        def on_click(self) -> None:
            self.ctrl.nudge()
            self.sig_nudge.emit()


    class MyApp(QtSession):
        stage_ctrl: AsPresenter[StagePresenter]
        stage_view: AsView[StageView]

        def wire(self) -> Iterator[Link]:
            yield self.stage_view.sig_nudge, self.stage_ctrl.nudge
    ```

    The session can't see which methods a component calls, so when it builds it
    names every component that holds another and is also connected to it:

    ```text
    'stage_view' holds 'stage_ctrl' and is also connected to it; a bundle reaches a component one way, by calling it or by a signal
    ```

    The two ways may also do different things, which is allowed, and the log
    line only asks you to check. Asking for a value a component shares, such as
    a `PlanSpec`, doesn't count as holding the component and logs nothing.

## Connect a coroutine

An `async def` method is a slot like any other:

```python
class MotorPresenter:
    @slot
    async def move(self, motor: str, position: float) -> None:
        await self.devices[motor].set(position)
```

The session delivers it differently from a plain method:

- it runs on `redsun`'s shared event loop, not on the thread that emitted;
- the emitter does not wait for it to finish;
- an error inside it is logged, and later emissions are still delivered.

If you need the emitter to wait, connect a plain method that calls
`run_coro(...)` from `redsun.aio` instead. To stop a task such a slot started,
for instance from a stop button, use `cancel_task(task)` from `redsun.aio`.
Called from another thread, it waits for the task to pause rather than
cancelling it while it runs.

Every session installs the async backend
[`psygnal`](../explanation/glossary.md#psygnal) needs for coroutine slots when
it is built, and removes it at shutdown.

## Address a signal group

A component keeping its signals in a [`SignalGroup`][psygnal.SignalGroup]
offers each member as a port, under the member's name:

```python
class FrameSignals(SignalGroup, strict=True):
    median = Signal(object)
    filtered = Signal(object)


class MedianPresenter:
    def __init__(self, name: str) -> None:
        self.name = name
        self.frames = FrameSignals(instance=self)
```

=== "Session class"

    ```python
    def wire(self) -> Iterator[Link]:
        yield self.median_ctrl.frames.median, self.img_widget.update_layers
    ```

=== "Session file"

    The path skips the group:

    ```yaml
    wiring:
      median_ctrl.median: img_widget.update_layers
    ```

Pass `instance=self` when making the group, or the session cannot tell which
component owns the signal.

## Choose the thread a slot runs on

A slot runs on the thread that emitted, unless something says otherwise. The
session looks for the thread in this order:

1. `@slot(thread=...)`, for one method;
2. `__redsun_slot_thread__` on the class, for every slot of it;
3. the session's frontend, through
   [`Frontend.thread_of`][redsun.Frontend.thread_of]: the Qt frontend runs a
   widget's slots on the main thread, since a widget may only be used from
   there.

A session with no frontend skips the third step. A slot that is a
coroutine function runs on the session's event loop whatever the frontend.

## Observe a device signal

[Device signals](../explanation/glossary.md#device-signal) come from
[`ophyd-async`](../explanation/glossary.md#ophyd-async), not `psygnal`. `wire`
tells the two apart by the signal's type, so a link to a device signal is
yielded the same way as one to a `psygnal` signal:

```python
class MyApp(QtSession):
    detector: AsDevice[MyDetector]
    temperature_widget: AsView[TemperatureView]

    def wire(self) -> Iterator[Link]:
        yield self.detector.temperature, self.temperature_widget.update_temperature
```

The slot receives each reading. The subscription is released at shutdown.

## Inspect what is connected

`connections` lists every link the session made, with the thread a slot runs
on when it isn't the one that emitted:

```python
for link in app.connections:
    print(link)
```

```
det_ctrl.sig_new_data -> img_widget.update_layers  [thread=main]
det_widget.sig_property_changed -> det_ctrl.configure
detector.temperature -> temperature_widget.update_temperature  [thread=main]
```

A link from a device signal is listed with the others, under the device and
the name of the signal within it.

A component may hold an object with signals or slots of its own as an
attribute. The session records that object under the name of the component.
It records a link yielded as
`self.det_widget.sig_action_request, self.det_ctrl.actions.request` as:

```
det_widget.sig_action_request -> det_ctrl.request
```

[`ports`][redsun.ports.ports] lists what one component offers:

```python
>>> ports(view).slots
{'update_layers': <bound method ImageView.update_layers ...>}
```

## Find what is not connected

A wrong port name fails the build, but a forgotten connection fails nowhere,
because the signal just reaches nothing.
[`unconnected`][redsun.Session.unconnected] finds it:

```python
print(app.unconnected)
```

```
det_ctrl.sig_error -> nothing
nothing -> img_widget.clear
```

An entry is not always a mistake: a component may offer more than a session
uses.

## Read a failure

A wrong connection stops the build and names both ends. The exception is a
connection to a component that failed to build: the session logs it, skips it
and still makes the other connections.

```text
Not connecting mover.sig_moved -> panel.on_moved: component 'panel' was not built
```

| message | cause |
| --- | --- |
| `AttributeError: 'DetectorPresenter' object has no attribute 'sig_typo'` | in `wire`: the signal name is wrong |
| `... is not connectable; mark it with the 'slot' decorator` | the method has no `@slot` |
| `cannot connect a.sig -> b.port: ...` | `psygnal` refused the arguments: wrong count, or wrong type |
| `'a.sig' names component 'a', which was not built. Built: ...` | the file names a component nobody declared |
| `'a' exposes no signal named 'sig'. ...` | the signal name in the file is wrong |
| `'a' exposes no slot named 'port'. ...` | the slot name is wrong, or the method is not marked |
| `wire returned nothing; it yields each link as a signal and a slot` | `wire` has no `yield` and returns `None` |
| `... is not a signal; a link is a psygnal signal or a device signal, then the slot it reaches` | the first item of a yielded link is not a signal |
| `wiring.det_ctrl.sig_new_data.str: Input should be a valid string` | a signal maps to something other than a slot path or a list of them; raised as [`ConfigurationError`][redsun.ConfigurationError] when the file is read |

## Pair two components

Two components whose slots name the signals of the other connect with one
line, `pairs: - [a, b]` in the file or
`yield from links_between(self.a, self.b)` in `wire`. The `pairs` section
runs after `wiring`. [Offer a pairing](offer-a-pairing.md) shows how a
component offers one.
