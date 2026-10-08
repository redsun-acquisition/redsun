---
icon: lucide/list-ordered
---

# How a session works

A [session](glossary.md#session) is one running application. It knows which
[components](glossary.md#component) to make, makes them in the right order,
connects them, and takes them apart again when it ends.

You write a session as a class:

```python
from collections.abc import Iterator
from typing import Annotated

from redsun import AsDevice, AsPresenter, AsView, Declare, Link
from redsun.qt import QtSession


class MyApp(QtSession):
    config = "session.yaml"

    stage: AsDevice[MyStage]
    motor_ctrl: AsPresenter[MotorPresenter]
    motor_widget: Annotated[AsView[MotorView], Declare(step_size=5.0)]

    def wire(self) -> Iterator[Link]:
        yield self.motor_ctrl.sig_moved, self.motor_widget.refresh


MyApp().run()
```

Each annotated line is a [declaration](glossary.md#declaration): the name on
the left becomes the component's name, and `AsDevice`, `AsPresenter` or
`AsView` says which [layer](glossary.md#layer) it belongs to and which class to
make. Once the session is built, `self.motor_ctrl` holds the `MotorPresenter`
it made, and your editor and `mypy` see it as one.

## Devices, presenters, views

A session has three layers of components, the [DVP](glossary.md#dvp) pattern,
and the [services](services.md) below them reach the hardware. Point at a
layer to read what it holds:

```d2 title="The layers of a session"
...@diagrams/style
grid-columns: 1
grid-gap: 24
app: session process {
  grid-columns: 1
  grid-gap: 0
  views: "views\nwhat the user sees and touches" {
    class: layer
    width: 420
    tooltip: A view holds the widgets. It shows what devices and presenters report, and turns what the user does into a signal a presenter acts on. It may hold presenters and devices.
  }
  presenters: "presenters\ndecide what happens and when" {
    class: layer
    width: 420
    tooltip: A presenter runs plans, computes results from the documents a run produces, moves devices when asked, and keeps the state the application needs. It may hold devices, never a view.
  }
  devices: "devices\nthe signals of your setup" {
    class: layer
    width: 420
    tooltip: Each device is an ophyd-async device, a set of signals such as a position or an exposure time. It knows what can be controlled, not when or why.
  }
}
services: "services\ntheir own programs, reached by prefix\nover Channel Access or PVAccess" {
  class: process
  width: 420
  tooltip: A service talks to the hardware and offers it to the devices under a prefix. The session starts the ones it launches before anything else and stops them after every component. A device that needs no hardware, such as a simulated stage, needs no service.
}
hardware: {
  class: hardware
  width: 420
}
```

The session builds the layers in that order, and a component's constructor or
`setup` can take only what its own layer or an earlier one owns. So a view may
take presenters and devices, while a presenter never holds a view, which is why
a presenter runs without a screen, in a test for example. Signals and slots
are not bound by the order: they connect components across layers in either
direction. [Components](components.md) explains what each layer may contain.

Services are separate programs, not components the session builds. The
session starts the ones it launches before anything else and stops them after
every component.

## What a build does

[`build`][redsun.Session.build] reads the
[configuration](glossary.md#configuration), gets the
[frontend](glossary.md#frontend) ready, then runs the
[build steps](glossary.md#build-step) in a fixed order:

```d2 title="The build steps"
...@diagrams/style
label: "Thirteen steps, always in this order. Step through them to see what each one does."
grid-rows: 2
grid-gap: 30
build: "" {
  grid-rows: 3
  grid-columns: 5
  grid-gap: 36
  style.stroke-width: 0
  style.fill: transparent
  configuration: "read the\nconfiguration" {class: step; width: 130; height: 56}
  runtime: "get the\nfrontend ready" {class: step; width: 130; height: 56}
  services: services {class: step; width: 130; height: 56}
  devices: devices {class: step; width: 130; height: 56}
  connect: connect {class: step; width: 130; height: 56}
  seal: seal {class: step; width: 130; height: 56}
  setup: setup {class: step; width: 130; height: 56}
  views: views {class: step; width: 130; height: 56}
  presenters: presenters {class: step; width: 130; height: 56}
  registry: registry {class: step; width: 130; height: 56}
  wiring: wiring {class: step; width: 130; height: 56}
  presentation: presentation {class: step; width: 130; height: 56}
  report: report {class: step; width: 130; height: 56}
  gap1: {class: gap; width: 130; height: 56}
  gap2: {class: gap; width: 130; height: 56}
  configuration -> runtime -> services -> devices -> connect -> registry -> presenters -> views -> setup -> seal -> wiring -> presentation -> report
}
detail: "" {
  width: 820
  height: 240
  grid-rows: 1
  grid-gap: 70
  style.stroke-dash: 4
}
scenarios: {
  configuration: {
    label: "The session reads its files and mappings in order, merges them, and checks the result once, listing every problem it finds."
    build.configuration.class: current
    detail.common: |yaml
      # common.yaml
      presenters:
        motor_ctrl:
          step: 2.0
    | {class: file}
    detail.sim: |yaml
      # simulation.yaml
      session: my-lab
    | {class: file}
    detail.checked: "merged and checked" {class: step}
    detail.common -> detail.checked
    detail.sim -> detail.checked
  }
  runtime: {
    label: "Before any component exists, the session sets the backend that runs coroutine slots. A QtSession also makes the QApplication here."
    build.runtime.class: current
    detail.backend: "backend for\ncoroutine slots" {class: step}
    detail.qapp: "QApplication\nQtSession only" {class: step}
  }
  services: {
    label: "Every launched service starts at once, and the session waits for each one's ready line. A session whose storage names a catalog starts its tiled server too."
    build.services.class: current
    detail.ioc: "camera_ioc\nstarted with python -m" {class: process}
    detail.session: session {class: step}
    detail.tiled: "tiled server\nif storage has a catalog" {class: process}
    detail.session -> detail.ioc
    detail.session -> detail.tiled
  }
  devices: {
    label: "Each device is made with its name and its settings, plus its service's prefix and the path provider when its constructor takes them. One that raises is left out."
    build.devices.class: current
    detail.code: |python
      stage = MyStage(name="stage", prefix="ST:")
      camera = MyCamera(name="camera", path_provider=paths)
    | {class: step}
  }
  connect: {
    label: "The devices connect all at once. A device that hasn't answered after 10 seconds is left out, like one that failed to build."
    build.connect.class: current
    detail.stage: stage {class: step}
    detail.out: "no answer in 10 s:\nleft out" {class: failed}
    detail.camera: camera {class: step}
    detail.ioc: "camera_ioc" {class: process}
    detail.camera -> detail.ioc: "connect()"
    detail.stage -> detail.out: "connect()"
  }
  registry: {
    label: "The registry collects what a constructor can ask for by type, before the first presenter is made."
    build.registry.class: current
    detail.settings: "SessionConfig\nSettings" {class: step}
    detail.devices: "DeviceMapping\nDevicesOf[P]" {class: step}
    detail.paths: "path provider\ncatalog address" {class: step}
    detail.shared: "what the\nproviders share" {class: step}
  }
  presenters: {
    label: "Each presenter gets its constructor arguments by type and from the files. What it shares with provides is registered as soon as it is made."
    build.presenters.class: current
    detail.code: |python
      class MotorPresenter:
          def __init__(self, name: str, *, devices: DeviceMapping, step: float = 1.0): ...

          @provides
          def readings(self) -> MotorReadings: ...
    | {class: step}
  }
  views: {
    label: "Each view is made the same way. In a QtSession it also gets the main window as its parent."
    build.views.class: current
    detail.code: |python
      class MotorView(QWidget):
          def __init__(self, name: str, parent: QWidget): ...
    | {class: step}
  }
  setup: {
    label: "Every setup runs now that all presenters and views exist, in declaration order, and gets what it asks for by type."
    build.setup.class: current
    detail.code: |python
      class RoiPresenter:
          def setup(self, readings: MotorReadings) -> None:
              self.readings = readings
    | {class: step}
  }
  seal: {
    label: "The session records what was built, notes the settings it would save, and closes itself to further building."
    build.seal.class: current
    detail.record: "record what\nwas built" {class: step}
    detail.note: "note the settings\nit would save" {class: step}
    detail.close: "close to more\nbuilding" {class: step}
    detail.record -> detail.note -> detail.close
  }
  wiring: {
    label: "Signals are connected to slots: the links wire yields, then the wiring section of the files, then the pairs."
    build.wiring.class: current
    detail.code: |python
      def wire(self) -> Iterator[Link]:
          yield self.motor_ctrl.sig_moved, self.motor_widget.refresh
    | {class: step}
  }
  presentation: {
    label: "A QtSession puts every view in its main window, where its placement says. A plain Session shows nothing."
    build.presentation.class: current
    detail.window: "main window" {
      grid-columns: 2
      dock: "Dock(\"left\")\nmotor_widget" {class: step}
      central: "Central()" {class: step}
    }
  }
  report: {
    label: "The session logs a summary of what it built and what it left out."
    build.report.class: current
    detail.log: |text
      Session built: 2/2 devices, 1/1 presenters, 1/1 views
    | {class: step}
  }
}
```

The shared values `registry` collects come from the session's
[providers](glossary.md#provider), classes made only to share
[values](glossary.md#shared-value). The settings `seal` notes let the session
tell later whether you [changed any](../how-to/save-a-session.md).

The order never changes. A frontend can change what happens inside a step,
never which steps run: `presentation` does nothing in a plain `Session`, while
`QtSession` shows the main window and its views there.

### Components that fail to build

A component that fails to build is left out, and so is anything built from
it; the session carries on with the rest:

```d2 title="A device that fails to build"
...@diagrams/style
direction: right
stage: {class: step}
camera: {class: step}
stage_ctrl: {class: step}
camera_ctrl: {class: step}
camera_view: {class: step}
stage_ctrl -> stage: takes
camera_ctrl -> camera: takes
camera_view -> camera_ctrl: takes
steps: {
  1: {camera: "camera\nconstructor raised" {class: failed}}
  2: {camera_ctrl: "camera_ctrl\nleft out" {class: failed}}
  3: {
    camera_view: "camera_view\nleft out" {class: failed}
  }
}
```

Here the camera's constructor can't find the serial port it talks through:

```python
class MyCamera(StandardReadable):
    def __init__(self, name: str = "", *, port: str = "COM3") -> None:
        raise OSError(f"serial port {port} not found")


class MyApp(Session):
    stage: AsDevice[MyStage]
    camera: AsDevice[MyCamera]
    stage_ctrl: AsPresenter[StagePresenter]
```

The session logs the error, and the summary at the end names what is missing:

```bash
$ uv run python my_session.py
[07-10-26|22:15:21][ERROR]: Failed to build device 'camera': serial port COM3 not found (_base.py:1581)
[07-10-26|22:15:21][WARNING]: Session built: 1/2 devices, 1/1 presenters, 0/0 views
Not built: camera (device) (_base.py:878)
```

A mistake in the session itself, such as a malformed `wiring` section, still
stops the build, and a [strict](glossary.md#strict-session) session stops
whenever something is missing.
[How to find out why a component is missing](../how-to/find-a-missing-component.md)
shows how to read the summary and make a session strict.
[ADR 11](decisions/0011-tolerating-a-component-that-fails-to-build.md) records
why the session carries on.

Two cases only log a warning: a component that shares nothing, asks for nothing
and isn't wired to anything, and a shared value no component asks for. Neither
is a mistake while you're still putting a session together, or when a
[plugin](glossary.md#plugin) ships more than your session uses.

## Shutting down

Each build step registers how to undo what it did, at the moment it does it.
These [releases](glossary.md#release) run in reverse order when you call
[`shutdown`][redsun.Session.shutdown]:

```d2 title="What shutdown undoes, in order"
...@diagrams/style
direction: right
connections: {class: step}
components: "components\nnewest first" {class: step}
devices: {class: step}
services: {class: step}
logs: "log files" {class: step}
connections -> components -> devices -> services -> logs
steps: {
  1: {connections.class: done}
  2: {components.class: done}
  3: {devices.class: done}
  4: {services.class: done}
  5: {logs.class: done}
}
```

The connections go first, so no signal calls a slot of a component that is
shutting down. A build that fails halfway runs the same releases, so it never
leaves a service running. You can call `shutdown` twice, and build the session
again afterwards.

## The configuration

You can describe a session in one of two ways: declare its components in a
Python class, or list them all in a [session file](glossary.md#session-file).
Either way, the settings come from the files and mappings the session reads.

=== "Declared in a class"

    The components and their classes live in your code, where your editor and
    `mypy` can check them. Files are optional. When the class lists some in
    `config`, they supply the session name and the arguments of the components
    the class declares, each under the component's name:

    ```python
    class MyApp(QtSession):
        config = "session.yaml"

        motor_ctrl: AsPresenter[MotorPresenter]
    ```

    ```yaml
    session: my-lab

    presenters:
      motor_ctrl:
        step: 2.0
    ```

    A file can also add a component the class doesn't declare, by naming the
    [plugin](plugins.md) that provides it, as
    [Components from a file and from a class](plugins.md#components-from-a-file-and-from-a-class)
    shows.

=== "Described in a file"

    Every component comes from a plugin, and you need no class of your own:

    ```python
    from redsun import Session

    app = Session.from_config("session.yaml").build()
    ```

    ```yaml
    session: my-lab
    frontend: qt

    devices:
      stage:
        plugin_name: mylab
        plugin_id: stage
    ```

    The `frontend` key picks the class the session is built on, so a file
    naming `qt` comes up as a `QtSession`. With no class name to fall back on,
    the files must set `session`.
    [Run a session without a GUI](../how-to/run-without-a-gui.md) shows a file
    that names no frontend.

### Merging the sources

A session reads its sources in order and merges them: a later source wins, and
nested sections merge key by key, except for a component's entry, which a later
source replaces whole:

```d2 title="Two files merged"
...@diagrams/style
grid-rows: 2
grid-columns: 2
grid-gap: 60
common: |yaml
  # common.yaml
  session: my-lab
  presenters:
    motor_ctrl:
      step: 2.0
      speed: 1.0
| {class: file}
simulation: |yaml
  # simulation.yaml
  presenters:
    motor_ctrl:
      step: 0.5
| {class: hidden}
check: "checked before\nanything is built" {class: hidden}
merged: |yaml
  # merged
  session: my-lab
  presenters:
    motor_ctrl:
      step: 0.5
| {class: hidden}
steps: {
  1: {
    simulation.class: file
    common -> simulation: then
  }
  2: {
    merged.class: file
    simulation -> merged: "motor_ctrl replaced\nwhole: speed is gone"
  }
  3: {
    check.class: current
    merged -> check
  }
}
```

`schema_version`, `frontend` and `services.transport` say what kind of session
this is, so every source must agree on them; a different value is an error. A
subclass adds its sources after its base class's, so you write shared settings
once:

```python
class Instrument(QtSession):
    config = "common.yaml"


class Simulation(Instrument):
    config = "simulation.yaml"  # read after common.yaml
```

!!! tip "Every mistake in the configuration at once"

    The check runs on the merged result. A misspelled key or a value of the
    wrong type raises [`ConfigurationError`][redsun.ConfigurationError], which
    lists every problem as `section.key: what`.
    [Session file](../reference/session-file.md) lists every key.

## Session name

You set the name with the `session` key; without it, the session is named after
its class. The name reaches three places:

```d2 title="Where the session name is used"
...@diagrams/style
direction: right
name: "session name" {class: current}
folder: "folder for data,\ncatalog and logs" {class: step}
app: "application that\nmenus and commands\nare registered on" {class: step}
settings: "file with one user's\nsaved settings" {class: file}
name -> folder
name -> app
name -> settings
```

## Log files

Each run writes its log to a file under `logs/<session>` in the root folder the
session's data goes under, and each launched service writes to a file of its
own beside it. The files follow the root if it moves while the session runs,
and close last at shutdown.
[Configure logging](../how-to/configure-logging.md#find-a-sessions-log-file)
shows the layout.

## Session protocols

A session is written against two [protocols](glossary.md#protocol), and the
classes `redsun` ships fill them in:

```d2 title="Session protocols and classes"
...@diagrams/style
direction: up
buildable: BuildableSession {
  shape: class
  "one method per build step"
}
desktop: DesktopSession {
  shape: class
  "window"
  "run()": "build, show the window, start the event loop"
}
session: Session {
  shape: class
  "start_runtime()": "set the backend of coroutine slots"
  "present()": "does nothing"
}
qt: QtSession {
  shape: class
  "start_runtime()": "also make the QApplication"
  "present()": "show the main window and views"
}
session -> buildable: implements
desktop -> buildable: extends
qt -> session: extends
qt -> desktop: implements
```

A session with no frontend shows nothing, which is what a test wants: `build()`
alone gives you every component without opening a window.
