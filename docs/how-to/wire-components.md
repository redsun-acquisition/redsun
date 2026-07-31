# Wire components together

Components do not connect themselves. A presenter declares signals, a view
declares signals and connectable methods, and the **application** says which
signal reaches which method.

## Mark a method as connectable

Decorate it with [`slot`][redsun.virtual.slot]. Only a marked method can be
connected, so marking one makes it public API: its name and its signature are
what other components are connected against.

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

- `name` is the port name used in a configuration file. It defaults to the
  method name without leading underscores, and exists so the method can be
  renamed without breaking a configuration.
- `thread` overrides the thread the slot is delivered on.

Signals need no marker. Every public [`Signal`][psygnal.Signal] attribute is
already a port.

## Connect a coroutine

An `async def` method is a slot like any other. Mark it and connect it; nothing
else changes.

```python
class MotorPresenter(Presenter):
    @slot
    async def move(self, motor: str, position: float) -> None:
        await self.devices[motor].set(position)
```

```yaml
wiring:
  - from: motor_widget.sig_motor_move
    to: motor_ctrl.move
```

Dispatch differs from a plain method in three ways:

- the coroutine runs on redsun's shared event loop, not on the thread that
  emitted;
- the emitter does not wait for it. The emission returns as soon as the
  coroutine is scheduled;
- an exception inside it is logged on the `redsun` logger instead of
  propagating back to the emitter, and later emissions keep being delivered.

If the last two matter, keep a sync method that owns the call and connect that
instead:

```python
    @slot
    def move(self, motor: str, position: float) -> None:
        run_coro(self.move_async(motor, position))
```

!!! warning

    The async backend must be installed before the wiring phase, or psygnal
    rejects the coroutine at connect. `QtAppContainer.build` calls
    [`set_async_backend`][redsun.aio.set_async_backend] for you; a plain
    `AppContainer` does not, so call it yourself before `build`.

## Declare the connections in Python

Override [`wire`][redsun.containers.AppContainer.wire] on the container. Every
component is built by the time it runs, and reads back as the attribute it was
declared under:

```python
class MyApp(QtAppContainer, config="session.yaml"):
    det_ctrl = declare_presenter(DetectorPresenter)
    img_widget = declare_view(ImageView)
    det_widget = declare_view(DetectorView)

    def wire(self) -> None:
        self.connect(self.det_ctrl.sig_new_data, self.img_widget.update_layers)
        self.connect(self.det_widget.sig_property_changed, self.det_ctrl.configure)
```

Fan-in is another line, not another concept: a second producer of frames reaches
the same viewer by adding one `connect` call.

## Declare the connections in YAML

A session built with `AppContainer.from_config` has no `wire` method to
override. Use the `wiring` section instead, addressing each end as
`component.port`:

```yaml
schema_version: 1.0
frontend: pyqt
session: my-session

presenters:
  det_ctrl:
    plugin_name: my-plugin
    plugin_id: detector

views:
  img_widget:
    plugin_name: my-plugin
    plugin_id: image

wiring:
  - from: det_ctrl.sig_new_data
    to: img_widget.update_layers
```

The component name is the key it was declared under, in the file or in the
container class. A signal port is the signal's attribute name; a slot port is
the name the slot declares.

Both forms end in the same call, so a container may use both: `wire` runs first,
then the `wiring` section.

## Address a signal group

A component whose signals live in a [`SignalGroup`][psygnal.SignalGroup]
exposes each **member** as a port, under the member name. The group attribute
itself is not a port.

```python
class FrameSignals(SignalGroup, strict=True):
    median = Signal(object)
    filtered = Signal(object)


class MedianPresenter(Presenter):
    def __init__(self, name: str, devices: Mapping[str, Device], /) -> None:
        super().__init__(name, devices)
        self.frames = FrameSignals(instance=self)
```

```yaml
wiring:
  - from: median_ctrl.median
    to: img_widget.update_layers
  - from: median_ctrl.filtered
    to: img_widget.update_layers
```

and in Python, through the group attribute:

```python
        self.connect(self.median_ctrl.frames.median, self.img_widget.update_layers)
```

!!! warning

    Pass `instance=self` when building the group. Without it the container
    cannot tell which component owns the signal, and the wiring report names
    the group instead of the component.

Group members and plain signals share one port namespace, so a member named
after an existing public signal on the same class raises
[`WiringError`][redsun.virtual.WiringError] when the ports are read.

## Choose the thread a slot runs on

Thread affinity belongs to the component, not to the connection. A class
declares it once:

```python
class MyView(View):
    __redsun_slot_thread__ = "main"
```

Every slot on that class is then delivered on the main thread. `@slot(thread=...)`
overrides it for one method, and `connect(..., thread=...)` overrides both.

`QtView` already declares `"main"`, so a Qt widget's slots need nothing.

## Inspect what is connected

```python
for link in app.virtual_container.connections:
    print(link)
```

```
det_ctrl.sig_new_data -> img_widget.update_layers  [thread=main]
det_widget.sig_property_changed -> det_ctrl.configure
```

[`ports`][redsun.virtual.ports] answers the other half, what a component
offers:

```python
>>> ports(view).slots
{'update_layers': <bound method ImageView.update_layers ...>}
```

Connections are recorded, so `AppContainer.shutdown` releases them.

## Read a failure

Every way of getting a connection wrong fails at build, naming both ends.

| Message | Cause |
|---|---|
| `... is not connectable; mark it with the 'slot' decorator` | the method exists but has no `@slot` |
| `cannot connect a.sig -> b.port: Cannot connect slot ...` | psygnal rejected the signature: wrong argument count, or wrong type against a signal that names one |
| `'a.sig' names component 'a', which was not built. Built: ...` | the configuration names a component the session did not load |
| `'a' exposes no slot named 'port'. Its slot ports: ...` | the port name is wrong, or the method was never marked |
| `'a.b.c' is not a port path; expected 'component.port'` | malformed path in the configuration |
