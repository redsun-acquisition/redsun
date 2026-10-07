---
icon: lucide/boxes
---

# How devices, presenters and views fit together

A [component](glossary.md#component) is a device, a presenter or a view. This
page explains what each one is for, and how the session gives a component the
things it needs.

## Where each argument comes from

The session makes each component by calling its constructor and passing every
argument by keyword. It fills each parameter from one of these places:

- `name` is always the component's name.
- If the [session file](glossary.md#session-file) or an inline `Declare(...)`
  gives a value for the parameter, the parameter takes that value.
- Any other parameter is looked up **by its type**, among what the session
  holds before any component exists: its settings (`SessionConfig`,
  `Settings`), the devices (`DeviceMapping`, `DevicesOf[P]`), the path
  provider, the catalog address, and the
  [shared values](glossary.md#shared-value) of its
  [providers](glossary.md#provider), classes made only to share values.
  [Share a value no component owns](../how-to/share-a-value.md#share-a-value-no-component-owns)
  shows how to add one.
- A Qt view's `parent` is the main window, which the frontend passes in; see
  [Frontends](frontends.md#the-qt-frontend).
- A parameter with a default keeps its default when nothing else fills it.

```python
class MotorPresenter:
    def __init__(self, name: str, *, devices: DeviceMapping, step: float = 1.0) -> None:
        self.name = name
        self.devices = devices
        self.step = step
```

If the file gives `step`, the presenter gets that value, and otherwise it gets
`1.0`. You never write code to choose between the two.

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
components in doesn't matter. `setup` must be an ordinary method, not
`async def`.

If a constructor asks for another component, the session refuses it before
anything is built, and the error tells you to move the parameter to `setup`.

If `setup` raises, the session logs the error and keeps the component, but
without whatever `setup` was going to give it. The build summary lists the
component under `Not set up`. The same happens when `setup` asks for a
component that was declared but failed to build.

The build stops with `TypeError` only when `setup` asks for something that
nothing in the session declares. No component failed in that case. The
mistake is in how the session is written, so you fix the session.

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

The session calls the method once, right after it makes the component, so the
method returns what the constructor built. Since a type names one value, two
components can't share values of the same type.
[Share a value](../how-to/share-a-value.md) shows the details, including
optional values.

### Using a protocol without importing redsun

A [plugin](glossary.md#plugin) can satisfy a `redsun`
[protocol](glossary.md#protocol) without importing `redsun`. The session
checks a component only by its members, meaning their names and, for methods,
their signatures, and never asks which module the protocol came from. A plugin
can also copy the protocol's definition into its own code, so that its type
checker sees it, without depending on `redsun` for that.

Whether a copy is enough depends on the types its members name. `Axis`,
`Light`, `DescribesAxes` and `DescribesLights` name only `ophyd-async`,
`bluesky` or built-in types, so you can copy them whole. `HasPlans` names
`PlanEntry`, `HasActions` names `ActionManager` and `DescribesPlans` names
`PlanSpec`, so a component using those protocols works with those `redsun`
types. A shared value is found by its exact type, so asking for the
`RunEngine`, or for [`Deferrals`][redsun.engine.Deferrals], which applies a
setting change during a plan without corrupting what the plan records, needs
`redsun`'s own classes.

## Devices

A [device](glossary.md#device) is an [`ophyd-async`](glossary.md#ophyd-async)
device, meaning a subclass of `ophyd_async.core.Device`. `redsun` adds nothing
to the device [layer](glossary.md#layer), so for signals, detectors and the
base classes, see the `ophyd-async` documentation.

Your devices describe what the setup contains and what can be controlled.
Reaching the hardware is best left to a [service](glossary.md#service), and
[Devices and services](services.md#devices-and-services) explains why the two
are kept apart.

The session makes a device as `cls(name=<name>, **kwargs)`, so every
`ophyd-async` device works, including one whose first parameter is `prefix`.
The one exception is a device that takes `name` only by position (after a
`/`): the session can't make it, and leaves it out.

### Connecting

Once the devices are made, the session connects them all at once and waits up
to ten seconds for each. A device that doesn't connect is left out, just like
one that failed to build, and the summary lists it as `camera (device, not
connected)`.

If you declare a device with [`autoconnect=False`](glossary.md#autoconnect),
the session leaves it unconnected, so your session's code can connect it when
it chooses. The build
then can't leave the device out because its hardware is missing, so a
component has to decide what to do when the connection fails. See
[How to connect a device on demand](../how-to/connect-a-device-on-demand.md).

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
command as a signal, and when the user asks, a presenter triggers it on every
device of the service. The devices stay connected throughout. The service
decides what letting go means, and takes the hardware back when it gets
another command.

## Presenters

A [presenter](glossary.md#presenter) holds the session's application logic. It
may run [`bluesky`](glossary.md#bluesky) [plans](plans.md), react to the
[documents](glossary.md#document) a run produces, move a device directly, or
talk to another program. Because it never touches a widget, it works without a
screen.

Any class can be a presenter if its constructor takes `name` as a keyword and
its instances keep that `name`. It doesn't inherit anything from `redsun`.

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

By convention, signal names start with `sig_`. A slot must be marked with
`slot`, and since other code connects to it by name, it's part of the
component's public interface. A slot may be `async def`.

The session makes the connections, either in [`wire`][redsun.Session.wire] or
from the file's `wiring` section; the components never connect themselves.
[Wire components together](../how-to/wire-components.md) shows both ways. A
slot on a Qt widget runs on the main thread, since a widget may only be used
from there. A slot can choose another thread with `@slot(thread=...)`.

When you write a presenter and a view for each other, each slot can say which
signal of the other one reaches it. The session then connects the two with one
[pairing](glossary.md#pairing), as
[Offer a pairing](../how-to/offer-a-pairing.md) shows.

## Cleaning up

If a component needs to clean up, give it a `shutdown` method, plain or
`async`. The session calls it when the session shuts down, newest component
first, and nothing else is needed.

A device can define one too, to leave its hardware in a safe state:

```python
class MyLaser(StandardReadable):
    async def shutdown(self) -> None:
        await self.intensity.set(0)
```

The session shuts the devices down after every presenter and view, which may
still use them in their own `shutdown`, and before the services stop, so each
device can still reach its service.

A device that didn't connect is left out of the session, and its `shutdown`
isn't called, since it would write to hardware that never answered. A device
declared with `autoconnect=False` is shut down, because a component may have
connected it.

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
