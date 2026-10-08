---
icon: lucide/boxes
---

# How devices, presenters and views fit together

A [component](glossary.md#component) is a device, a presenter or a view. This
page explains what each one is for, and how the session gives a component the
things it needs.

## Where each argument comes from

The session makes each component by calling its constructor and passing every
argument by keyword. Step through the diagram to see where each parameter of
this presenter gets its value:

```python
class MotorPresenter:
    def __init__(self, name: str, *, devices: DeviceMapping, step: float = 1.0) -> None:
        self.name = name
        self.devices = devices
        self.step = step
```

```d2 title="Where the arguments of MotorPresenter come from"
...@diagrams/style
direction: right
declared: "the declared name\nmotor_ctrl" {class: hidden}
held: "what the session holds,\nlooked up by type" {class: hidden}
default: "the default\n1.0" {class: hidden}
file: "session file\nor Declare(...)" {class: hidden}
ctor: "MotorPresenter(...)" {
  name: "name" {class: step; width: 220}
  devices: "devices: DeviceMapping" {class: step; width: 220}
  step: "step: float = 1.0" {class: step; width: 220}
}
declared -> ctor.name {style.opacity: 0}
held -> ctor.devices: "by its type" {style.opacity: 0}
default -> ctor.step: "otherwise" {style.opacity: 0}
file -> ctor.step: "if it gives step" {style.opacity: 0}
steps: {
  1: {
    declared.class: current
    (declared -> ctor.name)[0].style.opacity: 1
  }
  2: {
    declared.class: step
    held: {
      class: current
      tooltip: "What exists before any component does. The settings (SessionConfig, Settings), the devices (DeviceMapping, DevicesOf[P]), the path provider, the catalog address, and the values the session's providers share."
    }
    (held -> ctor.devices)[0].style.opacity: 1
  }
  3: {
    held.class: step
    file.class: current
    (file -> ctor.step)[0].style.opacity: 1
  }
  4: {
    file.class: step
    default.class: current
    (default -> ctor.step)[0].style.opacity: 1
  }
}
```

A [session file](glossary.md#session-file) or an inline `Declare(...)` that
gives `step` wins, and otherwise `step` keeps its default of `1.0`. You never
write code to choose between the two. The values the session holds by type
include the [shared values](glossary.md#shared-value) of its
[providers](glossary.md#provider), classes made only to share values;
[Share a value no component owns](../how-to/share-a-value.md#share-a-value-no-component-owns)
shows how to add one. A Qt view also gets the main window as its `parent`,
which the frontend passes in; see [Frontends](frontends.md#the-qt-frontend).

!!! warning "The session can't see types imported under `if TYPE_CHECKING:`"

    The session reads each parameter's annotation while the program runs, to decide
    what to pass. A type you import only under `if TYPE_CHECKING:` doesn't
    exist at that point, so the session leaves the component out and logs a
    `TypeError`. Import the types of these parameters with a normal import;
    [Limitations](limits.md#can-i-import-parameter-types-under-if-type_checking)
    lists where this applies.

### What arrives in `setup`

A constructor runs before the other components exist, so it can't receive one
of them. When a component needs another component, or a value another
component shares, it asks for it in an optional `setup` method:

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

The session calls every `setup` once all the presenters and views exist, and
fills its parameters by type in the same way, so the order you declare
components in doesn't matter. `setup` must be an ordinary method: the session
leaves out a component whose `setup` is `async def`.

What happens when `setup` can't get what it asks for depends on whose mistake
it is:

```d2 title="When setup can't get what it asks for"
...@diagrams/style
direction: right
raises: "setup raises" {class: step}
failed: "asks for a component\nthat failed to build" {class: step}
missing: "asks for something\nnothing declares" {class: step}
later: "asks for a component\nof a later layer" {class: step}
early: "the constructor asks\nfor a component" {class: step}
kept: "component kept,\nlisted under Not set up" {
  class: current
  tooltip: "The session logs the error and runs the component without what setup was going to give it."
}
stops: "the build stops\nwith TypeError" {
  class: failed
  tooltip: "No component failed. The mistake is in how the session is written, so you fix the session. The error says what to change, such as moving a constructor parameter to setup."
}
raises -> kept
failed -> kept
missing -> stops
later -> stops
early -> stops
```

The build checks a constructor that asks for a component, and a `setup` that
asks for one of a later [layer](glossary.md#layer), before anything is built.

### Sharing a value

A component offers a [shared value](glossary.md#shared-value) to the others by
marking a method with [`provides`][redsun.provides], and the method's return
type is what the others ask for:

```python
class MotorPresenter:
    def __init__(self, name: str) -> None:
        self.name = name
        self._readings = MotorReadings()

    @provides
    def readings(self) -> MotorReadings:
        return self._readings
```

```d2 title="How a shared value reaches another component"
...@diagrams/style
direction: down
motor: "make MotorPresenter" {class: current}
call: "call readings()\nonce" {class: hidden}
value: "the MotorReadings\nit returns" {class: hidden}
roi: "RoiPresenter.setup(readings)" {class: hidden}
motor -> call: "right after" {style.opacity: 0}
call -> value {style.opacity: 0}
value -> roi: "by its type" {style.opacity: 0}
steps: {
  1: {
    motor.class: done
    call.class: current
    (motor -> call)[0].style.opacity: 1
  }
  2: {
    call.class: done
    value.class: current
    (call -> value)[0].style.opacity: 1
  }
  3: {
    value.class: done
    roi.class: current
    (value -> roi)[0].style.opacity: 1
  }
}
```

The session calls the method right after it makes the component, so the
method returns what the constructor built. A type names one value, so when two
components share values of the same type, the build stops with a `TypeError`.
[Share a value](../how-to/share-a-value.md) shows the details, including
optional values.

### Using a protocol without importing redsun

A [plugin](glossary.md#plugin) can satisfy a `redsun`
[protocol](glossary.md#protocol) without importing `redsun`. The session
checks a component only by its members, meaning their names and, for methods,
their signatures, and never asks which module the protocol came from. A plugin
can also copy the protocol's definition into its own code, so that its type
checker sees it, without depending on `redsun` for that.

Whether a copy is enough depends on the types its members name:

| protocol | names | a copy works alone |
| --- | --- | --- |
| `Axis`, `Light` | `ophyd-async` and `bluesky` types only | yes |
| `DescribesAxes`, `DescribesLights` | `AxisInfo` or `LightInfo`, and `Configuration`, from `redsun.utils.devices` | no |
| `HasPlans` | `PlanEntry` | no |
| `HasActions` | `ActionManager` | no |
| `DescribesPlans` | `PlanSpec` and `CallbackType` | no |

A component using the last four works with those `redsun` types. A shared
value is found by its exact type, so asking for the `RunEngine`, or for
[`Deferrals`][redsun.engine.Deferrals], which applies a setting change during
a plan without corrupting what the plan records, needs `redsun`'s own classes.

## Devices

A [device](glossary.md#device) is an [`ophyd-async`](glossary.md#ophyd-async)
device, meaning a subclass of `ophyd_async.core.Device`. `redsun` adds nothing
to the device [layer](glossary.md#layer), so for signals, detectors and the
base classes, see the `ophyd-async` documentation.

Your devices are a model of your whole setup: what it contains and what can
be controlled, as a tree of devices and their signals. Reaching the hardware
is best left to a [service](glossary.md#service), and
[Devices and services](services.md#devices-and-services) explains why the two
are kept apart.

The session makes and connects every device the same way. Step through the
cases to see which devices end up in the session:

```d2 title="How the session makes and connects a device"
...@diagrams/style
direction: down
declaration: "declaration\nAsDevice[MyCamera]" {class: step; width: 260; height: 70}
make: "make\ncls(name=..., **kwargs)" {
  class: step
  width: 260
  height: 70
  tooltip: "The arguments come from the session file or Declare(...), plus the prefix of the device's service and the path provider when the constructor takes them."
}
connect: "connect\nall at once, up to 10 s each" {class: step; width: 260; height: 70}
kept: "in the session" {class: step; width: 260; height: 70}
out: "left out" {class: step; width: 300; height: 70}
declaration -> make
make -> connect
connect -> kept
make -> out: "constructor raised,\nor no service prefix"
connect -> out: "didn't connect"
make -> kept: "autoconnect=False"
scenarios: {
  connects: {
    make.class: current
    connect.class: current
    kept.class: current
  }
  raised: {
    make: "make\nconstructor raised" {class: failed}
    out: "left out\nFailed to build device" {class: failed}
  }
  "not connected": {
    connect: "connect\nno answer in 10 s" {class: failed}
    out: "left out\ncamera (device, not connected)" {class: failed}
  }
  "autoconnect=False": {
    connect.class: done
    kept: "in the session\nnot connected" {class: current}
  }
}
```

The session makes a device as `cls(name=<name>, **kwargs)`, so every
`ophyd-async` device works, including one whose first parameter is `prefix`.
The one exception is a device that takes `name` only by position (after a
`/`): the session can't make it, and leaves it out.

### Connecting

A device that doesn't connect is left out, just like one that failed to build.
If you declare a device with [`autoconnect=False`](glossary.md#autoconnect),
the session leaves it unconnected, so your session's code can connect it when
it chooses. The build then can't leave the device out because its hardware is
missing, so a component has to decide what to do when the connection fails.
See [How to connect a device on demand](../how-to/connect-a-device-on-demand.md).

### Talking to a service

When you declare a device with `service="stage_ioc"`, the device gets that
[service's](services.md) [prefix](glossary.md#prefix) as its `prefix`
argument. If the service isn't declared, didn't start, or has no prefix, the
session leaves the device out.

### Where a device writes

A device writes its own data files, in the format it or its service chooses.
If its constructor takes `path_provider`, the device gets the session's
[path provider](glossary.md#path-provider), which puts every file of a
session under one folder, named after the session, the day, the
[data key](glossary.md#data-key) and the plan. That way you find all the files
of a session in one place, whatever wrote them.
[How to choose where acquisition files go](../how-to/choose-where-files-go.md)
sets the folder and the names, and
[ADR 13](decisions/0013-acquisition-storage-belongs-to-the-device.md) records
why the device writes the data and not `redsun`.

### Standby

A service that holds hardware, such as a camera, can let go of it and keep
running, as long as it offers a command for that as a
[process variable](glossary.md#process-variable). A device exposes the
command as a signal, and when the user asks, your presenter triggers it on
every device of the service; the session has no standby step of its own. The
devices stay connected throughout. The service decides what letting go means,
and takes the hardware back when it gets another command.

## Presenters

A [presenter](glossary.md#presenter) holds the session's application logic. It
may run [`bluesky`](glossary.md#bluesky) [plans](plans.md), react to the
[documents](glossary.md#document) a run produces, move a device directly, or
talk to another program. Because it never touches a widget, it works without a
screen.

Any class can be a presenter if its constructor takes `name` as a keyword and
its instances keep that `name`. It doesn't inherit anything from `redsun`, and
it can't be an `ophyd-async` device.

## Views

A [view](glossary.md#view) holds the widgets, and says where it wants to be
shown with a [placement](glossary.md#placement), such as `Dock("left")`.

The placement is what makes a class a view: a view has one and a presenter
doesn't. Before anything is built, the [frontend](glossary.md#frontend)
checks that it can show the placement and that the view is the right kind of
object for it. [Frontends](frontends.md) covers placements and the Qt rules,
and [How to place a view in the window](../how-to/place-a-view.md) shows how
to set one.

## Signals and slots

Components talk to each other through [signals](glossary.md#signal) and
[slots](glossary.md#slot). They never call each other directly, unless one
received the other in `setup`:

```python
from psygnal import Signal

from redsun import slot


class MotorPresenter:
    sig_moved = Signal(str, float)


class MotorView(QWidget):
    @slot
    def refresh(self, motor: str, position: float) -> None: ...
```

```d2 title="A signal connected to a slot"
...@diagrams/style
direction: down
sig_moved: "MotorPresenter.sig_moved\nSignal(str, float)" {class: step}
refresh: "MotorView.refresh\nmarked with @slot" {
  class: step
  tooltip: "Runs on the main thread, because a Qt widget may only be used from there. @slot(thread=...) picks another thread."
}
sig_moved -> refresh: "the session connects them,\nin wire or the wiring section"
```

By convention, signal names start with `sig_`. A slot must be marked with
`slot`, and since other code connects to it by name, it's part of the
component's public interface. A slot may be `async def`.

The session makes the connections, either in [`wire`][redsun.Session.wire] or
from the file's `wiring` section; the components never connect themselves.
[Wire components together](../how-to/wire-components.md) shows both ways.

When you write a presenter and a view for each other, each slot can say which
signal of the other one reaches it. The session then connects the two with one
[pairing](glossary.md#pairing), as
[Offer a pairing](../how-to/offer-a-pairing.md) shows.

## Cleaning up

If a component needs to clean up, give it a `shutdown` method, plain or
`async`, and the session calls it when the session shuts down. A device can
define one too, to leave its hardware in a safe state:

```python
class MyLaser(StandardReadable):
    async def shutdown(self) -> None:
        await self.intensity.set(0)
```

```d2 title="The order components shut down in"
...@diagrams/style
direction: right
components: "presenters and views\nnewest first" {class: step}
devices: "devices" {
  class: step
  tooltip: "Every device that connected, and every device declared with autoconnect=False, since a component may have connected it. A device that didn't connect is left out of the session and never shut down, since it would write to hardware that never answered."
}
services: "services stop" {class: step}
components -> devices -> services
steps: {
  1: {components.class: current}
  2: {
    components.class: done
    devices.class: current
  }
  3: {
    devices.class: done
    services.class: current
  }
}
```

The devices go after every presenter and view, which may still use them in
their own `shutdown`, and before the services stop, so each device can still
reach its service.

## Dataclasses and pydantic models

A presenter can be a dataclass or a `pydantic` model, because the session
passes every argument by keyword, and `name` may be anywhere in the signature:

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

On a `pydantic` model, a signal must be a `ClassVar`, since `pydantic` refuses
a class attribute without an annotation. A value that `setup` assigns
shouldn't be a field: use `field(init=False)` on a dataclass, or a private
attribute on a model.

!!! warning "A class with `__slots__` and a signal is left out"

    `psygnal` refers to the component weakly, so a class with `__slots__`
    that owns a signal needs `__weakref__` among its slots, or the component
    is never freed. The session leaves such a class out, and the error names
    the fix: add `__weakref__` to the slots, or pass `weakref_slot=True` to a
    dataclass.

A Qt view can't be a `pydantic` model or a dataclass, because Qt needs its own
`QWidget.__init__` to run.

## Two components of the same class

Two stages, or two copies of one plot, are normal, and each declaration makes
its own component:

```python
class MyApp(QtSession):
    stage_x: AsDevice[MyStage]
    stage_y: AsDevice[MyStage]
```

Your code reaches each one by its name, as `self.stage_x`. A component that
needs every stage, however many there are, asks the session by what they can
do: see [Questions](questions.md).
