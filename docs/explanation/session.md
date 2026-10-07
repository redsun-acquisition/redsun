---
icon: lucide/list-ordered
---

# How a session build sequence works

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

Each annotated line is a [declaration](glossary.md#declaration). The name on
the left becomes the component's name, and the annotation says which
[layer](glossary.md#layer) the component belongs to and which class to make.
A line without `AsDevice`, `AsPresenter` or `AsView` is an ordinary
attribute, not a component.

Once the session is built, `self.motor_ctrl` holds the `MotorPresenter` the
session made. To your editor and `mypy`, `AsPresenter[MotorPresenter]` is still
the `MotorPresenter` type with a marker attached, so they see the same class.
The markers start with `As` so that each one says what it marks, and so that
none has the name of a class a component may itself subclass, such as
`Device`.

## Devices, presenters, views

A session is split into three layers, which together form the
[DVP](glossary.md#dvp) pattern:

```mermaid
graph LR
    D[devices] --> P[presenters] --> V[views]
```

- **Devices** talk to hardware. They are
  [`ophyd-async`](glossary.md#ophyd-async) devices.
- **Presenters** hold the behaviour: they run plans, compute things from the
  data, and drive the devices.
- **Views** show things on screen and pass on what the user does.

The session builds the layers in that order, and a component may only use what
its own layer or an earlier one owns. A presenter never knows about a view,
which is what lets it run without a screen, for example in a test.
[Components](components.md) explains what each layer may contain.

## What a build does

[`build`][redsun.Session.build] runs a fixed list of steps. It first reads the
[configuration](glossary.md#configuration) and gets the
[frontend](glossary.md#frontend) ready (for Qt, the `QApplication`). Then it
runs the [build steps](glossary.md#build-step) in this order:

| step | what happens |
| --- | --- |
| `services` | start the [services](services.md) the session launches, and the catalog |
| `devices` | make every device |
| `connect` | connect the devices, all at once |
| `registry` | collect what a component's constructor can ask for by type, such as the settings, the devices, and the [shared values](glossary.md#shared-value) of the session's providers, classes made only to share values |
| `presenters` | make the presenters |
| `views` | make the views |
| `setup` | call each component's `setup` method |
| `seal` | record which components were built, and close the session to further building. It also notes the settings each component would [save](../how-to/save-a-session.md) now, so the session can later tell whether you changed any |
| `wiring` | connect the [signals](glossary.md#signal) to the [slots](glossary.md#slot) |
| `presentation` | put the views on screen |
| `report` | log a summary of what was built |

The order never changes. A frontend can change what happens inside a step, but
never which steps run. The `presentation` step, for example, does nothing in a
plain `Session`, while `QtSession` uses it to show the main window and its
views.

### Failed components

If a device doesn't connect, or a presenter's constructor raises, the session
logs it and leaves that component out. The session carries on without it, and
the summary at the end says what is missing. Anything built from a missing
component is left out too. A mistake in the session itself, such as a
malformed `wiring` section, still stops the build.
[ADR 11](decisions/0011-tolerating-a-component-that-fails-to-build.md) records
why.

A [strict](glossary.md#strict-session) session stops instead, whenever
something is missing.
[How to find out why a component is missing](../how-to/find-a-missing-component.md)
shows how to read the summary and the log, and how to make a session strict.

A component nothing reaches, or a value nobody asks for, is logged as a
warning and kept. Neither is a mistake: a session under construction has
components nothing reaches yet, and a [plugin](glossary.md#plugin) may ship
one that a particular session doesn't use.

## Shutting down

Each step registers how to undo what it did, at the moment it does it: a
started service registers its stop, and a built component registers its
`shutdown`. These undo actions are the session's
[releases](glossary.md#release), and [`shutdown`][redsun.Session.shutdown]
runs them in reverse order:

```mermaid
graph LR
    W[connections] --> C[components, newest first] --> D[devices] --> S[services] --> L[log files]
```

The session undoes the connections first, so no signal calls a slot of a
component that is shutting down. A build that fails halfway runs the same
releases, so it never leaves a service running. You can safely call `shutdown`
twice, and you can build a session again after it was shut down.

## The configuration

A session reads its settings from the [session files](glossary.md#session-file)
and mappings listed in `config`. Each component's name is also its key in the
file:

```yaml
session: my-lab
frontend: qt

presenters:
  motor_ctrl:
    step: 2.0
```

The session reads the sources in order and merges them: a later source wins,
and nested sections merge key by key. Two rules are different:

- A component's entry is replaced whole. If a later file names `motor_ctrl`,
  it replaces every setting of `motor_ctrl`, since one file should own a
  constructor's arguments.
- `schema_version`, `frontend` and `services.transport` must agree across
  sources. They say what kind of session this is, so a later source giving a
  different value is an error.

A subclass adds its sources after its base class's, so you write shared
settings once:

```python
class Instrument(QtSession):
    config = "common.yaml"


class Simulation(Instrument):
    config = "simulation.yaml"  # read after common.yaml
```

The session checks the merged result before anything is built. A misspelled
key or a value of the wrong type raises
[`ConfigurationError`][redsun.ConfigurationError], which lists every problem
as `section.key: what`. [Session file](../reference/session-file.md) lists
every key.

### Sessions without a class

A file can describe a whole session, with every component taken from a
[plugin](plugins.md):

```python
from redsun import Session

app = Session.from_config("session.yaml").build()
```

The `frontend` key picks the class the session is built on, so a file naming
`qt` comes up as a `QtSession`. Such a session has no class name to fall back
on, so its file must set `session`.
[Run a session without a GUI](../how-to/run-without-a-gui.md) shows a file
that names no frontend at all.

## Session name

You set the session's name with the `session` key in the configuration. If you
leave it out, the session is named after its class. The session uses its name
for:

- the folder its data, catalog and log files go in;
- the application its menus and commands are registered on;
- the file where one user's [settings](../how-to/save-a-session.md) are kept.

## Log files

Each run writes its log to a file in the session's folder, and each launched
service writes to a file of its own beside it. The log files follow the data
folder if it moves while the session runs, and they close last at shutdown.
[Configure logging](../how-to/configure-logging.md) shows where they go.

## Session protocols

A session is written against two [protocols](glossary.md#protocol):

- [`BuildableSession`][redsun.BuildableSession] lists every build step as a
  method, and [`Session`][redsun.Session] implements them all. For the two
  steps that belong to a frontend, `Session` does the least a session needs:
  `start_runtime` sets the backend that coroutine slots run on, and `present`
  does nothing.
- [`DesktopSession`][redsun.DesktopSession] adds a window and `run`, which
  builds the session, shows the window and starts the event loop.

`QtSession` adds the `QApplication` to `start_runtime`, and fills `present`
with the main window and its views. A session with no frontend shows nothing,
which is what a test wants: `build()` alone gives you every component without
opening a window.
