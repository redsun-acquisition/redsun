# Wire components together

Components do not connect themselves. A presenter declares signals, a view
declares signals and connectable methods, and the **application** says which
signal reaches which method.

An application is declared in one of two ways, and each connection below is
shown in both. Picking a tab switches every tab on the site to the same form.

=== "Container class"

    A container subclass declares components as fields and connections by
    overriding [`wire`][redsun.containers.container.AppContainer.wire].

=== "Configuration file"

    A session built with `AppContainer.from_config` declares its components in
    YAML sections and its connections in the `wiring` section.

## Mark a method as connectable

Decorate it with [`slot`][redsun.virtual.slot]. Only marked methods can be
connected, so marking one makes its name and signature public API.

```python
from redsun.view import View
from redsun.virtual import slot


class ImageView(View):
    @slot
    def update_layers(self, readings: dict[str, Reading[Any]]) -> None:
        for key, reading in readings.items():
            self._layer(key).data = reading["value"]
```

Name a slot as you would any public method. `slot` accepts two options:

```python
    @slot(name="frames", thread="current")
    def update_layers(self, readings: dict[str, Reading[Any]]) -> None: ...
```

- `name` is the port name in a configuration file. It defaults to the method
  name without leading underscores, and lets the method be renamed without
  breaking a configuration.
- `thread` overrides the thread the slot runs on.

Signals need no marker: every public [`Signal`][psygnal.Signal] attribute is a
port.

## Declare the connections

=== "Container class"

    Every component is built when `wire` runs, available as the attribute it
    was declared under:

    ```python
    class MyApp(QtAppContainer, config="session.yaml"):
        det_ctrl = declare_presenter(DetectorPresenter)
        img_widget = declare_view(ImageView)
        det_widget = declare_view(DetectorView)

        def wire(self) -> None:
            self.connect(self.det_ctrl.sig_new_data, self.img_widget.update_layers)
            self.connect(self.det_widget.sig_property_changed, self.det_ctrl.configure)
    ```

    Each attribute has the type it was declared with, so a type checker sees
    `self.det_ctrl.sig_new_data` as a signal. A renamed or misspelled port is a
    type error before the application runs, and an `AttributeError` on its line
    if it reaches the build.

    `connect` does not raise for a component that failed to build. It returns
    `None` and logs the skipped link, and the other connections are made, so
    one broken panel does not break the rest of the wiring.

=== "Configuration file"

    Each end is addressed as `component.port`:

    ```yaml
    schema_version: 1.0
    frontend: pyqt
    name: my-session

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
        plugin_id: detector

    wiring:
      - from: det_ctrl.sig_new_data
        to: img_widget.update_layers
      - from: det_widget.sig_property_changed
        to: det_ctrl.configure
    ```

    The component name is its declared key. A signal port is the signal's
    attribute name; a slot port is the name the slot declares.

Fan-in is one more line: a second frame producer reaches the same viewer with
one more connection.

Both forms make the same call, so a container may use both: `wire` runs first,
then the `wiring` section.

## Connect a coroutine

An `async def` method is a slot like any other: mark it and connect it.

```python
class MotorPresenter(Presenter):
    @slot
    async def move(self, motor: str, position: float) -> None:
        await self.devices[motor].set(position)
```

=== "Container class"

    ```python
        def wire(self) -> None:
            self.connect(self.motor_widget.sig_motor_move, self.motor_ctrl.move)
    ```

=== "Configuration file"

    ```yaml
    wiring:
      - from: motor_widget.sig_motor_move
        to: motor_ctrl.move
    ```

It is delivered differently from a plain method:

- the coroutine runs on `redsun`'s shared event loop, not on the emitting
  thread;
- the emitter does not wait: emitting returns once the coroutine is scheduled;
- an exception inside it is logged on the `redsun` logger instead of reaching
  the emitter, and later emissions are still delivered.

If the last two matter, connect a sync method that makes the call:

```python
    @slot
    def move(self, motor: str, position: float) -> None:
        run_coro(self.move_async(motor, position))
```

!!! warning

    Install the async backend before wiring, or `psygnal` rejects the coroutine
    on connect. `QtAppContainer.build` calls
    [`set_async_backend`][redsun.aio.set_async_backend]; a plain `AppContainer`
    does not, so call it before `build`.

## Address a signal group

A component whose signals are in a [`SignalGroup`][psygnal.SignalGroup] exposes
each **member** as a port under its member name. The group attribute is not a
port.

```python
class FrameSignals(SignalGroup, strict=True):
    median = Signal(object)
    filtered = Signal(object)


class MedianPresenter(Presenter):
    def __init__(self, name: str, devices: Mapping[str, Device], /) -> None:
        super().__init__(name, devices)
        self.frames = FrameSignals(instance=self)
```

=== "Container class"

    Reach the member through the group attribute:

    ```python
    def wire(self) -> None:
        self.connect(self.median_ctrl.frames.median, self.img_widget.update_layers)
        self.connect(self.median_ctrl.frames.filtered, self.img_widget.update_layers)
    ```

=== "Configuration file"

    The port path is flat: component name, then member name, no group.

    ```yaml
    wiring:
      - from: median_ctrl.median
        to: img_widget.update_layers
      - from: median_ctrl.filtered
        to: img_widget.update_layers
    ```

!!! warning

    Pass `instance=self` when building the group. Without it the container
    cannot tell which component owns the signal, and the wiring report names
    the group instead.

Group members and plain signals share one port namespace, so a member with the
name of a public signal on the same class raises
[`WiringError`][redsun.virtual.WiringError] when the ports are read.

## Choose the thread a slot runs on

Thread affinity belongs to the component, not the connection. A class declares
it once:

```python
from typing import ClassVar

from redsun.virtual import SlotThread


class MyView(View):
    __redsun_slot_thread__: ClassVar[SlotThread] = "main"
```

Every slot of that class then runs on the main thread. `@slot(thread=...)`
overrides it for one method, and `connect(..., thread=...)` overrides both.

`QtView` already declares `"main"`, so Qt widget slots need nothing.

## Observe a device signal

Device signals come from `ophyd-async`, not `psygnal`, so `connect` does not
accept them. [`subscribe`][redsun.virtual.VirtualContainer.subscribe] does, with
the same guarantees:

```python
class TemperatureView(QtView):
    @slot
    def update_temperature(self, reading: dict[str, Reading[float]]) -> None:
        self._label.setText(f"{next(iter(reading.values()))['value']:.1f} C")


class MyApp(QtAppContainer):
    def wire(self) -> None:
        self.virtual_container.subscribe(
            self.detector.temperature, self.temperature_widget.update_temperature
        )
```

The slot must be marked, the thread affinity comes from the component, and the
subscription is released at shutdown. That matters more than for signals:
`ophyd-async` releases a subscription by identity, so the subscriber must keep
the exact callback object to undo it.

!!! note

    `ophyd-async` needs a running event loop to subscribe, and `wire` runs on the
    main thread; `subscribe` handles this.

## Inspect what is connected

```python
for link in app.virtual_container.connections:
    print(link)
for record in app.virtual_container.subscriptions:
    print(record)
```

```
det_ctrl.sig_new_data -> img_widget.update_layers  [thread=main]
det_widget.sig_property_changed -> det_ctrl.configure
temperature ~> temperature_widget.update_temperature  [thread=main]
```

`->` is a signal connection, `~>` a device subscription.

[`ports`][redsun.virtual.ports] lists what a component offers:

```python
>>> ports(view).slots
{'update_layers': <bound method ImageView.update_layers ...>}
```

Both are recorded, so `AppContainer.shutdown` releases them.

## Find what is *not* connected

A wrong port name fails at build. A forgotten connection fails nowhere: the
signal emits to nothing. `unconnected` finds it by subtracting the recorded
links from what every built component offers.

```python
report = app.virtual_container.unconnected
if report:
    print(report)
```

```
det_ctrl.sig_error -> nothing
nothing -> img_widget.clear
```

It is an [`Unconnected`][redsun.virtual.Unconnected] record, so a script can
assert on it:

```python
assert not app.virtual_container.unconnected.slots
```

An entry is not always a mistake: a component may offer more than an
application uses. The report lists what is unused, not what is wrong.

## Read a failure

A wrong connection fails at build, naming both ends. The exception is a
connection to a component that failed to build, in `wire` or the configuration
file: it is logged at `WARNING` and skipped, and the other connections are
made.

```
Not connecting mover.sig_motor_moved -> panel.on_moved: 'panel' not built
```

=== "Container class"

    | Message | Cause |
    |---|---|
    | `AttributeError: 'DetectorPresenter' object has no attribute 'sig_typo'` | the signal was renamed or misspelled |
    | `... is not connectable; mark it with the 'slot' decorator` | the method exists but has no `@slot` |
    | `cannot connect a.sig -> b.port: Cannot connect slot ...` | `psygnal` rejected the signature: wrong argument count, or wrong type against a signal that names one |

=== "Configuration file"

    | Message | Cause |
    |---|---|
    | `'a.sig' names component 'a', which was not built. Built: ...` | the file names a component it never declared |
    | `'a' exposes no signal named 'sig'. Its signal ports: ...` | the signal name is wrong |
    | `'a' exposes no slot named 'port'. Its slot ports: ...` | the port name is wrong, or the method was never marked |
    | `'a.b.c' is not a port path; expected 'component.port'` | malformed path |
    | `wiring entry 0 must be a mapping with exactly the keys 'from' and 'to'` | a rule is missing a key or carries an extra one |
    | `cannot connect a.sig -> b.port: Cannot connect slot ...` | `psygnal` rejected the signature |
