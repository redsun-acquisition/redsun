---
icon: lucide/cable
---

# How to wire components together

Components do not connect themselves. A presenter declares
[signals](../reference/glossary.md#signal), a view declares signals and
[slots](../reference/glossary.md#slot), and the
[session](../reference/glossary.md#session) says which signal reaches which
slot.

You can write the connections in the session class or in the session file;
each example below shows both. Picking a tab switches every tab on the site to
the same form.

=== "Session class"

    Override [`wire`][redsun.Session.wire] and call
    [`connect`][redsun.Session.connect].

=== "Session file"

    List the connections in the `wiring` section.

## Mark a method as a slot

Decorate it with [`slot`][redsun.slot]. Only marked methods can be connected,
so marking one makes its name and arguments public.

```python
from redsun import slot


class ImageView(QWidget):
    @slot
    def update_layers(self, readings: dict[str, Reading[Any]]) -> None:
        for key, reading in readings.items():
            self._layer(key).data = reading["value"]
```

`slot` takes two options:

```python
    @slot(name="frames", thread="current")
    def update_layers(self, readings: dict[str, Reading[Any]]) -> None: ...
```

- `name` is the port name a session file uses. It defaults to the method name
  without leading underscores, so you can rename the method without breaking a
  file.
- `thread` chooses the thread the slot runs on.

Signals need no marker: every public [`Signal`][psygnal.Signal] attribute is a
[port](../reference/glossary.md#port).

## Declare the connections

=== "Session class"

    Every component exists when `wire` runs, under the attribute it was declared
    as:

    ```python
    from redsun import AsPresenter, AsView
    from redsun.qt import QtSession


    class MyApp(QtSession):
        det_ctrl: AsPresenter[DetectorPresenter]
        img_widget: AsView[ImageView]
        det_widget: AsView[DetectorView]

        def wire(self) -> None:
            self.connect(self.det_ctrl.sig_new_data, self.img_widget.update_layers)
            self.connect(self.det_widget.sig_property_changed, self.det_ctrl.configure)
    ```

    Each attribute has the type it was declared with, so a misspelled signal is a
    type error before the program runs.

=== "Session file"

    Each end is written `component.port`:

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
      - from: det_ctrl.sig_new_data
        to: img_widget.update_layers
      - from: det_widget.sig_property_changed
        to: det_ctrl.configure
    ```

    A signal's port is its attribute name; a slot's port is the name the slot
    declares.

A session may use both: `wire` runs first, then the `wiring` section. The
[path provider](../reference/glossary.md#path-provider) can be wired too, as
`path_provider`.

## Connect a coroutine

An `async def` method is a slot like any other:

```python
class MotorPresenter:
    @slot
    async def move(self, motor: str, position: float) -> None:
        await self.devices[motor].set(position)
```

It is delivered differently from a plain method:

- it runs on `redsun`'s shared event loop, not on the thread that emitted;
- the emitter does not wait for it to finish;
- an error inside it is logged, and later emissions are still delivered.

If you need the emitter to wait, connect a plain method that calls
`run_coro(...)` from `redsun.aio` instead.

A `QtSession` installs the async backend `psygnal` needs for coroutine slots.
A plain `Session` does not: call
[`set_async_backend`][redsun.aio.set_async_backend] before `build`.

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
    def wire(self) -> None:
        self.connect(self.median_ctrl.frames.median, self.img_widget.update_layers)
    ```

=== "Session file"

    The path skips the group:

    ```yaml
    wiring:
      - from: median_ctrl.median
        to: img_widget.update_layers
    ```

Pass `instance=self` when making the group, or the session cannot tell which
component owns the signal.

## Choose the thread a slot runs on

A slot runs on the thread that emitted, unless something says otherwise. In
order, the thread comes from:

1. `connect(..., thread=...)`, for one connection;
2. `@slot(thread=...)`, for one method;
3. `__redsun_slot_thread__` on the class, for every slot of it;
4. the session's default: a `QtSession` runs a Qt widget's slots on the main
   thread, since a widget may only be used from there.

## Observe a device signal

Device signals come from `ophyd-async`, not `psygnal`, so `connect` does not
take them. [`subscribe`][redsun.Session.subscribe] does:

```python
class MyApp(QtSession):
    detector: AsDevice[MyDetector]
    temperature_widget: AsView[TemperatureView]

    def wire(self) -> None:
        self.subscribe(
            self.detector.temperature, self.temperature_widget.update_temperature
        )
```

The slot receives each reading. The subscription is released at shutdown.

## Inspect what is connected

```python
for link in app.connections:
    print(link)
for record in app.subscriptions:
    print(record)
```

```
det_ctrl.sig_new_data -> img_widget.update_layers  [thread=main]
det_widget.sig_property_changed -> det_ctrl.configure
temperature ~> temperature_widget.update_temperature  [thread=main]
```

`->` is a signal connection, `~>` a device subscription.
[`ports`][redsun.ports.ports] lists what one component offers:

```python
>>> ports(view).slots
{'update_layers': <bound method ImageView.update_layers ...>}
```

## Find what is not connected

A wrong port name fails the build. A forgotten connection fails nowhere: the
signal just reaches nothing. [`unconnected`][redsun.Session.unconnected]
finds it:

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

A wrong connection stops the build and names both ends. A connection to a
component that failed to build is the exception: it is logged and skipped,
and the other connections are still made.

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
| `wiring.0.to: Field required` | a rule is missing a key; raised as [`ConfigurationError`][redsun.ConfigurationError] when the file is read |
