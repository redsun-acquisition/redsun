---
icon: lucide/server
---

# How to write a service

Write a [service](../explanation/glossary.md#service) for a session to
launch, declare it, and point a device at it. The tabs show a `caproto`
[IOC](../explanation/glossary.md#ioc) served over
[Channel Access](../explanation/glossary.md#channel-access) and a `fastcs`
controller served over [PVAccess](../explanation/glossary.md#pvaccess); the
rest of the page holds for both. [Services](../explanation/services.md)
explains what a service is and how a session handles it.

## Prerequisites

`redsun` depends on [`ophyd-async`](../explanation/glossary.md#ophyd-async)
and on nothing a control-system protocol needs, so a service brings its own,
and the device side its `ophyd-async` extra:

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

Besides serving its
[process variables](../explanation/glossary.md#process-variable), a service
that `redsun` launches must print a line when it is ready, stop when the
session asks, and listen only on the local machine.

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
      would on ++ctrl+c++. It does nothing when no session launched the IOC:
      run on its own without a terminal, a service may have its standard
      input closed from the start.
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
    - If serving fails first, the service raises what made it fail, and the
      session logs it.
    - [`configure_logging`][redsun.services.configure_logging] sends the
      records of `fastcs` to the session at the level the session records
      at. Do not call `fastcs.logging.configure_logging` after it: that
      replaces the output with coloured text, which the session reads as
      `DEBUG` lines.
    - Run alone, the service listens on every network interface of the
      machine. Launched by a session, it listens on `127.0.0.1` only, since
      the session sets `EPICS_PVAS_INTF_ADDR_LIST`; see
      [Environment variables](../reference/environment.md).
    - `fastcs` takes a prefix of letters, digits, `-` and `_`. `STAGE:` is
      accepted, since the last colon is taken off. `LAB:STAGE:` is refused.
    - Over PVAccess a prefix has to be the only one of its name on the
      machine: two sessions serving the same one find each other's records.

    `fastcs` prints no line of its own when it starts to serve, so the
    service finds out by asking.
    [`ready_when_reachable`][redsun.services.ready_when_reachable] asks for
    the record in which `fastcs` lists the attributes of the controller until
    it gets an answer, then prints the ready text the declaration gives. Any
    server of that name can answer, which is one more reason for a prefix of
    its own.

Closing standard input is how a session asks a service to stop, on every
platform. A service that blocks in a call of its own, as `caproto`'s `run`
does, calls `stop_on_request`; a service built on `asyncio` awaits
`wait_for_stop` instead.

If the session crashes, nobody reads the service's output any more, and
printing raises. Clean up before printing, or do not print.

Under `channel-access`, a launched service listens on a port the session
chooses when its process starts, and no other program is told which one, so
`caget` from another terminal does not find it. Under `pv-access`, another
program on the machine reaches it with `EPICS_PVA_ADDR_LIST=127.0.0.1`. A
service other machines must reach runs on its own, on the ports it is set to,
and the session attaches to it.

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

In the session class, beside the device that talks to it:

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
process is started with, and is how the `caproto` IOC learns the same prefix:
a service that calls [`identity`][redsun.services.identity], as the `fastcs`
one does, needs no `args` for it. `args` is a list, or a mapping of options:
`--` is put before each name, `true` passes the option alone, `false` leaves
it out, and a list passes each item after it. The
[session file reference](../reference/session-file.md) has the table.

`ready` is text the session waits for in the output of the service: the
first line containing it marks the service ready, so give text an error
message would not contain. Without `ready`, the session does not wait, and
connects the devices of a service that may not serve yet.

A service that prints no line of its own once it serves calls
[`ready`][redsun.services.ready], which prints the text the declaration gives,
so the text is written in one place. A PVAccess service can call
[`ready_when_reachable`][redsun.services.ready_when_reachable] with one of its
own process variables instead: it prints the text once that variable answers.

`Launch` is a service the session starts and stops. `Attach` is one already
running elsewhere: nothing starts or stops, and its devices only get its
[prefix](../explanation/glossary.md#prefix). Its devices find it by
searching the network, and through the address list of your environment.
When the search does not reach it, on another subnet for instance, give its
`address`: the session adds it to the address list of its transport before
any device connects. See
[Environment variables](../reference/environment.md).

The device gets the service's prefix as its `prefix` argument, so giving the
device a `prefix` of its own is refused. A device whose service did not start
is left out.

## Check that it starts

Run the session from the folder that holds the module of the service, since
that is where it looks for it. For the `fastcs` example, the session logs:

```text
Service 'stage_service' started
Services started: 1/1
```

## Serve several devices from one service

Every device naming a service gets the same prefix. The devices tell their
process variables apart by the rest of the name, which a constructor keyword
can carry:

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

A bundle can write the declaration once and share it:

```python
CameraIoc: TypeAlias = Annotated[
    AsService, Launch("mylab.iocs.camera", ready="Server startup complete.")
]


class MyApp(QtSession):
    camera_ioc: CameraIoc
```

A plugin can also list the service in its [manifest](../explanation/plugins.md),
so a session file names it without Python:

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

Every service of a session speaks one [transport](../explanation/glossary.md#transport),
`channel-access` unless the configuration says otherwise:

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
no device speaks both.
[Services](../explanation/services.md#one-transport-per-session) says what a
session does for each transport.

A launched process learns its name and prefix from
[`identity`][redsun.services.identity], so a module serving several sessions
needs no arguments for them. It returns `None` when no session launched the
process:

```python
from redsun.services import identity

me = identity()
prefix = me.prefix if me else ""
```

## React when it exits

A launched service that exits by itself sends `sig_exited` with its name and
exit code. A service is set on the session under its name, so `wire` can
connect it:

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

Without `thread="main"`, a presenter's slot runs on the thread reading the
service's output.

## Log from it

The service's output is logged under `redsun.service.<name>`, and written to
a log file of its own. A service calling
[`configure_logging`][redsun.services.configure_logging] at startup logs at
the level the session records at, and each record keeps its level instead of
arriving as a `DEBUG` line; see
[Log from a service](configure-logging.md#log-from-a-service).

## Quiet the type checker for `fastcs`

`fastcs` ships no `py.typed` file, so a type checker cannot see its types.
`mypy` reports the import:

```text
Skipping analyzing "fastcs.controllers": module is installed, but missing
library stubs or py.typed marker  [import-untyped]
```

and, in strict mode, the class written on top of it:

```text
Class cannot subclass "Controller" (has type "Any")  [misc]
```

To quiet both, add this to the configuration of `mypy` in `pyproject.toml`,
with the name of your module in the second entry:

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
