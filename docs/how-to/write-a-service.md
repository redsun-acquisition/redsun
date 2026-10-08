---
icon: lucide/server
---

# How to write a service

To have a session launch a [service](../explanation/glossary.md#service) of
your own, you write the service, declare it and point a device at it. The tabs
show a `caproto` [IOC](../explanation/glossary.md#ioc) served over
[Channel Access](../explanation/glossary.md#channel-access) and a `fastcs`
controller served over [PVAccess](../explanation/glossary.md#pvaccess), and the
rest of the page holds for both. [Services](../explanation/services.md)
explains what a service is and how a session handles it.

## Prerequisites

`redsun` depends on [`ophyd-async`](../explanation/glossary.md#ophyd-async)
but not on any control-system protocol, so you install the packages your
service needs, plus the `ophyd-async` extra for the device side:

=== "caproto"

    ```bash
    uv add caproto "ophyd-async[ca]"
    ```

=== "FastCS"

    ```bash
    uv add "fastcs[epicspva]" "ophyd-async[pva]"
    ```

    !!! note "Written for `fastcs` 0.14"

        The API of `fastcs` is still changing, and this page follows it. If
        a name on this page no longer exists in the version you installed,
        check the documentation of `fastcs`.

## Write the service

A service that `redsun` launches does three things besides serving its
[process variables](../explanation/glossary.md#process-variable): it prints a
line when it is ready, stops when the session asks, and listens only on the
local machine. Step through what the session and the service tell each other:

```d2 title="A launched service, from start to stop"
...@diagrams/style
label: "In its first build step, the session starts the service as a process of its own, with python -m and the module the declaration names."
shape: sequence_diagram
session: session {
  class: step
  tooltip: The session starts every launched service in its first build step, and stops them after every component at shutdown.
}
device: device {class: step}
service: service {
  class: process
  tooltip: A process of its own, started as python -m with the module the declaration names.
}
session -> service: "start python -m <module> <args>"
service -> session: "print the ready text" {style.opacity: 0}
session -> device: "build it with the prefix,\nthen connect it" {style.opacity: 0}
device -> service: "read and write the process\nvariables under the prefix" {
  style.opacity: 0
}
session -> service: "close standard input,\non every platform" {
  style.opacity: 0
}
service -> service: "clean up and exit" {style.opacity: 0}
steps: {
  1: {label: "The session waits until the service prints its ready text."; (service -> session)[0].style.opacity: 1}
  2: {label: "The session builds the device with the service's prefix, then connects it."; (session -> device)[0].style.opacity: 1}
  3: {label: "The device reads and writes the process variables under that prefix."; (device -> service)[0].style.opacity: 1}
  4: {label: "At shutdown, after every component, the session closes the service's standard input. This works the same on every platform."; (session -> service)[1].style.opacity: 1}
  5: {label: "The service cleans up and exits."; (service -> service)[0].style.opacity: 1}
}
```

=== "caproto"

    ```python
    # mylab/iocs/camera.py
    from caproto.server import PVGroup, ioc_arg_parser, pvproperty, run

    from redsun.services import stop_on_request


    class Camera(PVGroup):
        exposure = pvproperty(value=0.1, name="Exposure")


    if __name__ == "__main__":
        options, run_options = ioc_arg_parser(default_prefix="CAM:", desc="camera")
        stop_on_request()
        run(Camera(**options).pvdb, **{**run_options, "interfaces": ["127.0.0.1"]})
    ```

    - `caproto` prints `Server startup complete.` once it serves. The
      session waits for that line.
    - [`stop_on_request`][redsun.services.stop_on_request] turns the
      session's request to stop into `SIGINT`, so the IOC shuts down as it
      would on ++ctrl+c++. It does nothing when no session launched the IOC,
      because a service run on its own without a terminal may have its
      standard input closed from the start.
    - `127.0.0.1` keeps the launched IOC off the network.

=== "FastCS"

    `fastcs` describes a piece of hardware as a controller with attributes.
    `AttrRW` is an attribute that can be read and written, and `Float` says
    what it holds:

    ```{.python}
    --8<-- "docs/examples/stage_fastcs.py:controller"
    ```

    Then serve it:

    ```{.python}
    --8<-- "docs/examples/stage_fastcs.py:serve"
    ```

    - `FastCS` serves the controller over the transports it is given, here
      PVAccess.
    - [`identity`][redsun.services.identity] gives the
      [prefix](../explanation/glossary.md#prefix) the session declared, and
      the controller is served under it. Run alone, the service falls back
      on `STAGE:`.
    - [`wait_for_stop`][redsun.services.wait_for_stop] returns when the
      session asks the service to stop. Run alone, the service waits until
      ++ctrl+c++, and the `try` around `asyncio.run` keeps that stop from
      printing a traceback.
    - If serving fails first, the service raises the error and the session
      logs it.
    - [`configure_logging`][redsun.services.configure_logging] sends the
      records of `fastcs` to the session at the level the session records
      at. The session reads every line the service prints, and logs a line
      that isn't one of these records at `DEBUG`. So don't call
      `fastcs.logging.configure_logging`, the `fastcs` function of the same
      name, after the `redsun` one: it replaces the records with coloured
      text, which the session then logs as `DEBUG` lines.
    - Run alone, the service listens on every network interface of the
      machine. Launched by a session, it listens on `127.0.0.1` only, since
      the session sets `EPICS_PVAS_INTF_ADDR_LIST`; see
      [Environment variables](../reference/environment.md).
    - `fastcs` takes a prefix of letters, digits, `-` and `_`. `STAGE:` is
      accepted, since the last colon is taken off. `LAB:STAGE:` is refused.
    - Over PVAccess a prefix has to be the only one of its name on the
      machine: two sessions serving the same one find each other's records.

    `fastcs` prints no line of its own when it starts to serve, so the
    service has to ask.
    [`ready_when_reachable`][redsun.services.ready_when_reachable] keeps asking
    for the record in which `fastcs` lists the attributes of the controller.
    When it gets an answer, it prints the ready text the declaration gives.
    Any server serving a record of that name can answer, so if another
    session serves the same prefix, this service counts as ready too early.
    Give each service a prefix no other service on the machine uses.

Since the session asks a service to stop by closing its standard input, a
service that blocks in a call of its own, as `caproto`'s `run` does, calls
`stop_on_request`. A service built on `asyncio` awaits `wait_for_stop`
instead.

!!! warning "Printing after a session crash raises"

    If the session crashes, nobody reads the service's output any more, and
    printing raises. Clean up before you print, or don't print.

Under `channel-access`, a [launched
service](../explanation/glossary.md#launched-service) listens on a port the
session chooses when its process starts, and no other program is told which
one. A Channel Access client run from another terminal, such as `caget`,
doesn't find it. Under `pv-access`, another program on the machine reaches it
with `EPICS_PVA_ADDR_LIST=127.0.0.1`. If other machines must reach the service,
run it on its own, on the ports you set, and let the session attach to it.

## Point a device at it

=== "caproto"

    The device names each process variable under the prefix it receives:

    ```python
    from ophyd_async.core import StandardReadable
    from ophyd_async.epics.core import epics_signal_rw


    class MyCamera(StandardReadable):
        def __init__(self, prefix: str, name: str = "") -> None:
            with self.add_children_as_readables():
                self.exposure = epics_signal_rw(float, f"{prefix}Exposure")
            super().__init__(name=name)
    ```

    Under the prefix `CAM:`, `exposure` reads and writes `CAM:Exposure`.

=== "FastCS"

    ```{.python}
    --8<-- "docs/examples/device_fastcs.py:device"
    ```

    The device names no process variable.
    [`fastcs_connector`][ophyd_async.fastcs.core.fastcs_connector] reads the
    record that lists the attributes, and fills in every signal the device
    declares. For the attribute `position` under the prefix `STAGE:`,
    `fastcs` serves three records:

    | Record | Holds |
    | --- | --- |
    | `STAGE:PVI` | the list of the attributes |
    | `STAGE:Position` | the value to write |
    | `STAGE:Position_RBV` | the value to read |

## Declare it

Declare the service in the session class, beside the device that talks to it:

=== "caproto"

    ```python
    from typing import Annotated

    from redsun import AsDevice, AsService, Attach, Declare, Launch
    from redsun.qt import QtSession


    class MyApp(QtSession):
        camera_ioc: Annotated[
            AsService,
            Launch(
                "mylab.iocs.camera",
                ready="Server startup complete.",
                prefix="CAM:",
                args={"prefix": "CAM:"},
                stop_timeout=30,
            ),
        ]
        beamline: Annotated[AsService, Attach("BL01:", address="10.0.0.5")]
        camera: Annotated[AsDevice[MyCamera], Declare(service="camera_ioc")]
    ```

=== "FastCS"

    ```{.python}
    --8<-- "docs/examples/device_fastcs.py:declare"
    ```

    The line the session waits for is printed by the service, through
    `ready_when_reachable`. `config` names the PVAccess
    [transport](../explanation/glossary.md#transport); see
    [Name the transport](#name-the-transport).

`prefix` is what the devices of the service receive. `args` is what the
process is started with, which is how the `caproto` IOC learns the same
prefix. The `fastcs` service needs no prefix in `args`, because it reads the
prefix with [`identity`][redsun.services.identity].

`args` is a list, or a mapping of options. In a mapping, `--` goes before each
name, `True` passes the option alone, `False` leaves it out (`true` and `false`
in a session file), and a list passes each item after the option. For example,
`args={"prefix": "CAM:", "simulate": True, "debug": False}` starts the module
with `--prefix CAM: --simulate`. The [session file
reference](../reference/session-file.md) has the table.

`ready` is text the session waits for in the output of the service. The
first line containing it marks the service ready, so pick text an error
message would not contain.

!!! warning "Without `ready` the session doesn't wait"

    The session then connects the devices of a service that may not serve
    yet. Set `ready` on every launched service.

A service that prints no line of its own once it serves calls
[`ready`][redsun.services.ready], which prints the text the declaration gives,
so you write the text in one place. A PVAccess service can call
[`ready_when_reachable`][redsun.services.ready_when_reachable] with one of its
own process variables instead, and it prints the text once that variable
answers.

`Launch` declares a service the session starts and stops. `Attach` declares
one already running elsewhere: the session starts and stops nothing, and its
devices only get the service's [prefix](../explanation/glossary.md#prefix).
They find it by searching the network and through the address list of your
environment. When the search doesn't reach it, on another subnet for instance,
give its `address`, and the session adds it to the address list of its
transport before any device connects. See
[Environment variables](../reference/environment.md).

The device gets the service's prefix as its `prefix` argument, so the session
refuses a device that also gives a `prefix` of its own. A device whose service
didn't start is left out.

## Check that it starts

Run the session from the folder that holds the module of the service, since
that is where the session looks for it. For the `fastcs` example, the session
logs:

```text
Service 'stage_service' started
Services started: 1/1
```

## Serve several devices from one service

Every device naming a service gets the same prefix, so the devices tell their
process variables apart by the rest of the name. A constructor keyword can
carry it:

```python
from ophyd_async.core import StandardReadable
from ophyd_async.epics.core import epics_signal_rw


class Axis(StandardReadable):
    def __init__(self, prefix: str, axis: str, name: str = "") -> None:
        with self.add_children_as_readables():
            self.position = epics_signal_rw(float, f"{prefix}{axis}:Position")
        super().__init__(name=name)


class MyApp(QtSession):
    stage_ioc: Annotated[
        AsService,
        Launch("mylab.iocs.stage", ready="Server startup complete.", prefix="ST:"),
    ]
    x: Annotated[AsDevice[Axis], Declare(service="stage_ioc", axis="X")]
    y: Annotated[AsDevice[Axis], Declare(service="stage_ioc", axis="Y")]
```

`x` reads `ST:X:Position`, and `y` reads `ST:Y:Position`.

A package can define the declaration once, as a type alias, for every session
to reuse:

```python
CameraIoc: TypeAlias = Annotated[
    AsService, Launch("mylab.iocs.camera", ready="Server startup complete.")
]


class MyApp(QtSession):
    camera_ioc: CameraIoc
```

A plugin can also list the service in its [manifest](../explanation/plugins.md),
which lets a session file name it without Python:

```yaml
# mylab/redsun.yaml
services:
  camera-ioc:
    module: mylab.iocs.camera
    ready: "Server startup complete."
```

```yaml
# session.yaml
services:
  camera_ioc:
    plugin_name: mylab
    plugin_id: camera-ioc
    prefix: "CAM:"
  beamline:
    prefix: "BL01:"

devices:
  camera:
    plugin_name: mylab
    plugin_id: camera
    service: camera_ioc
```

`beamline` names no module, so the session attaches to it.

## Name the transport

All the services of a session speak one
[transport](../explanation/glossary.md#transport), `channel-access` unless the
configuration says otherwise:

```yaml
services:
  transport: pv-access
```

In a session class, put it in `config`:

```python
class MyApp(QtSession):
    config: ClassVar[dict[str, Any]] = {"services": {"transport": "pv-access"}}
```

An unknown transport, or two sources naming different ones, raises when the
configuration is read. The transport holds for every device of the session, so
a device can't speak both.
[Services](../explanation/services.md#one-transport-per-session) says what a
session does for each transport.

[`identity`][redsun.services.identity] gives a launched process the name and
the prefix its session declared for it. A module that several sessions launch,
each with its own prefix, reads them there and needs no `args` to pass them.
`identity` returns `None` when no session launched the process:

```python
from redsun.services import identity

me = identity()
prefix = me.prefix if me else ""
```

## React when it exits

A launched service that exits by itself sends `sig_exited` with its name and
exit code. The session holds each service under its name, so `wire` can
connect the signal to a slot:

```python
from collections.abc import Iterator

from redsun import AsPresenter, Link, slot
from redsun.log import Loggable


class CameraPresenter(Loggable):
    def __init__(self, name: str) -> None:
        self.name = name

    @slot(thread="main")
    def on_service_exited(self, name: str, code: int) -> None:
        self.logger.warning(f"{name} exited with code {code}")


class MyApp(QtSession):
    camera_ioc: CameraIoc
    presenter: AsPresenter[CameraPresenter]

    def wire(self) -> Iterator[Link]:
        yield self.camera_ioc.sig_exited, self.presenter.on_service_exited
```

Without `thread="main"`, the slot runs on the thread that reads the service's
output.

## Log from it

The service's output is logged under `redsun.service.<name>`, and written to
a log file of its own. A service calling
[`configure_logging`][redsun.services.configure_logging] at startup logs at
the level the session records at, and each record keeps its level instead of
arriving as a `DEBUG` line; see
[Log from a service](configure-logging.md#log-from-a-service).

## Quiet the type checker for `fastcs`

`fastcs` ships no `py.typed` file, so a type checker can't see its types.
`mypy` reports the import:

```text
Skipping analyzing "fastcs.controllers": module is installed, but missing
library stubs or py.typed marker  [import-untyped]
```

and, in strict mode, the class written on top of it:

```text
Class cannot subclass "Controller" (has type "Any")  [misc]
```

To quiet both, add this to the `mypy` configuration in `pyproject.toml`, with
the name of your module in the second entry:

```toml
[[tool.mypy.overrides]]
module = ["fastcs.*"]
ignore_missing_imports = true

[[tool.mypy.overrides]]
module = ["stage_fastcs"]
disable_error_code = ["misc"]
```

## The `fastcs` example in full

??? example "The service"

    ```{.python}
    --8<-- "docs/examples/stage_fastcs.py"
    ```

??? example "The session"

    The presenter and the view are the ones of the tutorial
    [Describing a device with a protocol](../tutorials/device-protocols.md).

    ```{.python}
    --8<-- "docs/examples/device_fastcs.py"
    ```
