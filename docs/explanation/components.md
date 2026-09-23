# Components

A [component](../reference/glossary.md#component) is a device, a presenter or
a view. This page explains what each one is, and how a component gets the
things it needs.

## Where each argument comes from

A session makes a component by calling its constructor with every argument
by keyword. It fills each parameter from one of these places:

- `name` is always the component's name.
- A parameter the [session file](../reference/glossary.md#session-file) or an
  inline `Declare(...)` mentions takes that value.
- Any other parameter is looked up **by its type**, among the values the
  session holds before any component exists: `SessionConfig`, `Settings`,
  `DeviceMapping`, `DevicesOf[P]`, the path provider, the catalog address,
  and whatever a plugin's providers share.
- A parameter with a default keeps it when nothing else fills it.

```python
class MotorPresenter:
    def __init__(self, name: str, *, devices: DeviceMapping, step: float = 1.0) -> None:
        self.name = name
        self.devices = devices
        self.step = step
```

`step` comes from the file if the file gives it, and is `1.0` if not. You
never write code to choose between the two.

A type used to look a parameter up has to be imported normally, not only
under `if TYPE_CHECKING:`, because the session reads the annotation while the
program runs.

### What arrives in `setup`

A constructor runs before the other components exist, so it cannot receive
one of them. A component that needs another component, or a value another
component shares, asks for it in an optional `setup` method:

```python
class RoiPresenter:
    def __init__(self, name: str) -> None:
        self.name = name

    def setup(self, readings: MotorReadings) -> None:
        self.readings = readings
```

The session calls every `setup` once all presenters and views exist, filling
its parameters by type the same way. So the order you declare components in
does not matter. `setup` must be an ordinary method, not `async def`.

A constructor asking for another component is refused before anything is
built, and the error tells you to move the parameter to `setup`.

A `setup` that raises is logged, and the component stays in the session
without what `setup` was going to give it. The build summary lists it under
`Not set up`.

### Sharing a value

A component offers a value to the others by marking a method with
[`provides`][redsun.provides]. The return type is what others ask for:

```python
class CameraPresenter:
    @provides
    def readings(self) -> MotorReadings:
        return self._readings
```

The session calls the method once, right after the component is made, so it
returns what the constructor built. Two components cannot share the same type:
a type names one value. [Share a value](../how-to/share-a-value.md) shows the
details, including optional values.

## Devices

A [device](../reference/glossary.md#device) is an `ophyd-async` device: a
subclass of `ophyd_async.core.Device`. `redsun` adds nothing to the device
layer, so see the `ophyd-async` documentation for signals, detectors and
the base classes.

A session makes a device as `cls(name=<name>, **kwargs)`, so every
`ophyd-async` device works, including one whose first parameter is `prefix`.
A device taking `name` only by position (after a `/`) cannot be made, and is
left out.

### Connecting

After making the devices, the session connects them all at once and waits up
to ten seconds for each. A device that does not connect is left out like one
that failed to build, and the summary lists it as `camera (device, not
connected)`.

A device declared with `autoconnect=False` is left unconnected, for the
session's code to connect when it chooses:

```python
class StagePresenter:
    sig_connected = Signal(str)

    def __init__(self, name: str, *, devices: DeviceMapping) -> None:
        self.name = name
        self.devices = devices

    @slot
    async def connect_stage(self) -> None:
        stage = self.devices["stage"]
        await stage.connect()
        self.sig_connected.emit(stage.name)
```

### Talking to a service

A device declared with `service="stage_ioc"` gets that
[service's](services.md) prefix as its `prefix` argument. If the service is
not declared, did not start, or has no prefix, the device is left out.

### Where a device writes

A device writes its own data files. A device whose constructor takes
`path_provider` gets the session's
[path provider](../reference/glossary.md#path-provider), which puts every file
of a session under one folder:

```
<base_dir>/<session>/<YYYY-MM-DD>/<datakey>/<plan>_<counter>
```

`base_dir` comes from the `storage` section of the session file, and is the
user's data folder when left out. A declaration cannot give `path_provider`
itself. A device that does not take it picks its own paths.

The path provider has three slots for the wiring:

```yaml
wiring:
  - from: acquisition.sig_pre_launch_notify
    to: path_provider.set_plan
  - from: acquisition.sig_plan_done
    to: path_provider.reset_plan
  - from: output_dir_widget.sig_directory_chosen
    to: path_provider.set_base_dir
```

`set_plan` names the files after the next run, and `reset_plan` goes back to
`unknown`. `set_base_dir` raises `RuntimeError` while a plan runs, and once
the session's catalog has started.
[ADR 13](decisions/0013-acquisition-storage-belongs-to-the-device.md) records
why the device, and not `redsun`, writes the data.

### Standby

A service holding hardware, such as a camera, can let go of it while it keeps
running, if it offers a command for that. A presenter triggers it:

```python
class HardwarePresenter:
    @slot
    async def standby(self) -> None:
        await asyncio.gather(
            *(camera.close_camera.trigger() for camera in self.cameras.values())
        )
```

The devices stay connected; the service decides what letting go means.

## Presenters

A [presenter](../reference/glossary.md#presenter) holds the session's
behaviour. It may run `bluesky` [plans](plans.md), react to the documents a
run produces, move a device directly, or talk to another program. It never
touches a widget, so it works without a screen.

A presenter is any class whose constructor takes `name` as a keyword and
whose instances keep that `name`. It inherits nothing from `redsun`.

## Views

A [view](../reference/glossary.md#view) holds the widgets. It says where it
wants to be shown with a [placement](../reference/glossary.md#placement):

```python
from qtpy.QtWidgets import QWidget

from redsun import Placement
from redsun.qt import Dock


class MotorView(QWidget):
    placement: Placement = Dock("left")

    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.name = name
```

The placement is what makes a class a view: a view has one and a presenter
does not. The frontend checks, before anything is built, that it can show the
placement and that the view is the right kind of object for it.
[Frontends](frontends.md) covers placements and the Qt rules.

## Signals and slots

Components talk to each other through [signals](../reference/glossary.md#signal)
and [slots](../reference/glossary.md#slot), and never call each other
directly unless they received each other in `setup`:

```python
from psygnal import Signal

from redsun import slot


class MotorPresenter:
    sig_moved = Signal(str, float)


class MotorView(QWidget):
    @slot
    def refresh(self, motor: str, position: float) -> None: ...
```

Signal names start with `sig_`. A slot must be marked with `slot`, which makes
its name public: other code connects to it. A slot may be `async def`.

The session connects them, in [`wire`][redsun.Session.wire] or in the file's
`wiring` section, never the components themselves.
[Wire components together](../how-to/wire-components.md) shows both. A slot
on a Qt widget runs on the main thread unless it says otherwise, since a
widget may only be used from there.

## Cleaning up

A component that needs to clean up defines `shutdown`, plain or `async`. The
session calls it when it shuts down, newest component first. Nothing else is
needed.

## Dataclasses and pydantic models

A presenter can be a dataclass or a pydantic model, since the session passes
every argument by keyword and `name` may be anywhere in the signature:

```python
@dataclass
class DataclassController:
    name: str
    step: float = 1.0


class ModelController(BaseModel):
    name: str
    step: float = 1.0
    sig_moved: ClassVar[Signal] = Signal(str)
```

On a pydantic model a signal must be a `ClassVar`, since pydantic refuses a
class attribute without an annotation. A value `setup` assigns should not be
a field: use `field(init=False)` on a dataclass, or a private attribute on a
model.

A class with `__slots__` that owns a signal needs `__weakref__` among its
slots, or `weakref_slot=True` on a dataclass. `psygnal` refers to the
component weakly, and without it the component is never freed. A class
missing it is left out, and the error names the fix.

A Qt view cannot be a pydantic model or a dataclass: Qt needs its own
`QWidget.__init__` to run.

## Two components of the same class

Two stages, or two copies of one plot, are normal. Each declaration is its own
component:

```python
class MyApp(QtSession):
    stage_x: AsDevice[MyStage]
    stage_y: AsDevice[MyStage]
```

Code reaches each by its name, `self.stage_x`. A component that needs "every
stage", however many there are, asks the session by what they can do: see
[Questions](questions.md).
