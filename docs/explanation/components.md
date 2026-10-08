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

No code of yours chooses between a [session file](glossary.md#session-file)
and the default. What the session holds by type includes the
[shared values](glossary.md#shared-value) of its
[providers](glossary.md#provider), classes made only to share values
([Share a value no component owns](../how-to/share-a-value.md#share-a-value-no-component-owns)),
and a Qt view also gets the main window as its `parent`
([Frontends](frontends.md#the-qt-frontend)).

!!! warning "The session can't see types imported under `if TYPE_CHECKING:`"

    The session reads the annotations while the program runs, when a type
    imported only under `if TYPE_CHECKING:` doesn't exist, so it leaves the
    component out and logs a `TypeError`. Import those types normally;
    [Limitations](limits.md#can-i-import-parameter-types-under-if-type_checking)
    lists where this applies.

### What arrives in `setup`

A constructor runs before the other components exist, so a component that
needs another, or a value another shares, asks for it in an optional `setup`:

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

Every `setup` runs once all presenters and views exist, filled by type, so a
component can ask for one declared after it. The calls run in declaration
order, though: a `setup` reading what another `setup` assigns sees it only if
that component is declared first. An `async def setup` gets the component left
out. When `setup` can't get what it asks for, the outcome depends on whose
mistake it is:

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

A type names one value, so two components sharing the same type stop the
build with a `TypeError`. [Share a value](../how-to/share-a-value.md) covers
optional values too.

### Using a protocol without importing redsun

The session checks a component only by its members' names and signatures,
never by where a [protocol](glossary.md#protocol) came from. So a
[plugin](glossary.md#plugin) can satisfy a `redsun` protocol, or copy its
definition for its own type checker, without importing `redsun`. A copy works
alone only when the types its members name do:

| protocol | names | a copy works alone |
| --- | --- | --- |
| `Axis`, `Light` | `ophyd-async` and `bluesky` types only | yes |
| `DescribesAxes`, `DescribesLights` | `AxisInfo` or `LightInfo`, and `Configuration`, from `redsun.utils.devices` | no |
| `HasPlans` | `PlanEntry` | no |
| `HasActions` | `ActionManager` | no |
| `DescribesPlans` | `PlanSpec` and `CallbackType` | no |

A shared value is found by its exact type too, so asking for the `RunEngine`
or for [`Deferrals`][redsun.engine.Deferrals], which applies a setting change
during a plan without corrupting what the plan records, needs `redsun`'s own
classes.

## Devices

A [device](glossary.md#device) is an [`ophyd-async`](glossary.md#ophyd-async)
device, a subclass of `ophyd_async.core.Device`; `redsun` adds nothing to the
device [layer](glossary.md#layer), so the `ophyd-async` documentation covers
signals and detectors. Your devices model your whole setup as a tree, and
reaching the hardware is best left to a [service](glossary.md#service), as
[Devices and services](services.md#devices-and-services) explains. Step
through the cases to see which devices end up in the session:

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

Making a device as `cls(name=<name>, **kwargs)` works for every `ophyd-async`
device, including one whose first parameter is `prefix`, except one that takes
`name` only by position (after a `/`), which is left out.

### Connecting

A device declared with [`autoconnect=False`](glossary.md#autoconnect) stays
unconnected for your code to connect when it chooses, so the build can't leave
it out for missing hardware: a component decides what to do when the
connection fails. See
[How to connect a device on demand](../how-to/connect-a-device-on-demand.md).

### Talking to a service

A device declared with `service="stage_ioc"` gets that
[service's](services.md) [prefix](glossary.md#prefix) as its `prefix`, and is
left out when the service isn't declared, didn't start or has no prefix.

### Where a device writes

A device writes its own data files, in the format it or its service chooses.
A constructor that takes `path_provider` gets the session's
[path provider](glossary.md#path-provider), which puts every file of a session
in one folder, named after the session, the day, the
[data key](glossary.md#data-key) and the plan.
[How to choose where acquisition files go](../how-to/choose-where-files-go.md)
sets the folder and the names, and
[ADR 13](decisions/0013-acquisition-storage-belongs-to-the-device.md) records
why the device writes the data and not `redsun`.

### Standby

A service holding hardware, such as a camera, can let go of it and keep
running if it offers a command for that as a
[process variable](glossary.md#process-variable). When the user asks, your
presenter triggers that command through the service's devices, which stay
connected; the session has no standby step of its own.

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

The placement is what makes a class a view. Before the build, the
[frontend](glossary.md#frontend) checks that it can show the placement and
that the view is the right kind of object for it; [Frontends](frontends.md)
covers the Qt rules, and [How to place a view](../how-to/place-a-view.md)
shows how to set one.

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

Signal names start with `sig_` by convention. A slot is marked with `slot`,
may be `async def`, and is part of the component's public interface, since
other code connects to it by name. Components never connect themselves;
[Wire components together](../how-to/wire-components.md) shows `wire` and the
`wiring` section. A presenter and a view written for each other can name the
signals that reach their slots, and the session connects them with one
[pairing](glossary.md#pairing) ([Offer a pairing](../how-to/offer-a-pairing.md)).

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
