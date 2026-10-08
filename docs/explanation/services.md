---
icon: lucide/server-cog
---

# How a session runs and talks to services

A service is a server your devices talk to, such as an
[EPICS](glossary.md#epics) [IOC](glossary.md#ioc), a camera server or a motion
controller's gateway. Your [`ophyd-async`](glossary.md#ophyd-async) devices
talk to it over [Channel Access](glossary.md#channel-access) or
[PVAccess](glossary.md#pvaccess) without `redsun` taking part. `redsun` does
the rest: it starts a launched service, notices when it exits, stops it
cleanly, and hands its [prefix](glossary.md#prefix) and transport to the
devices.

!!! warning "Devices without a service"

    You don't strictly need a service, since an `ophyd-async` device can
    reach its hardware on its own. For now, though, `redsun` supports such
    devices only in part, so a service is the preferred way to reach
    hardware. We will provide tutorials on wrapping third-party packages
    through `ophyd-async` in the future.

## Devices and services

A session splits your setup into devices and services, which know as little as
possible about each other. Point at a shape to read what it does:

```d2 title="Devices meet services at the prefix"
...@diagrams/style
direction: right
model: "the setup, as devices" {
  stage: "stage\nx, y" {
    class: step
    tooltip: A device is a set of signals that presenters and plans read and set. It says what can be controlled, not how to reach the hardware.
  }
  camera: "camera\nexposure, roi" {
    class: step
    tooltip: A device is a set of signals that presenters and plans read and set. It says what can be controlled, not how to reach the hardware.
  }
}
impl: "the hardware, as services" {
  stage_ioc: "stage service" {
    class: process
    tooltip: A service opens the serial port or the camera, speaks the vendor's protocol or runs the vendor's library, and offers the result as process variables. It knows nothing about the setup around it.
  }
  camera_ioc: "camera service" {
    class: process
    tooltip: A service opens the serial port or the camera, speaks the vendor's protocol or runs the vendor's library, and offers the result as process variables. It knows nothing about the setup around it.
  }
}
motors: "motor controller" {class: hardware}
sensor: "camera" {class: hardware}
model.stage -> impl.stage_ioc: "prefix ST:"
model.camera -> impl.camera_ioc: "prefix CAM:"
impl.stage_ioc -> motors
impl.camera_ioc -> sensor
```

The devices model your setup the way its users think of it, as an
`ophyd-async` tree: a microscope has a stage, the stage an X and a Y axis, each
axis a position. A service describes no setup; it only makes hardware
reachable, so the same model can sit on real hardware or on a simulation.

!!! note "One device for the whole setup"

    We intend each setup to be described by a single device at the root of
    such a tree, such as a `MyMicroscope` that holds its stage and its camera.
    For now, some features of `redsun` look only at the devices a session
    declares and not at their children, so declare each piece a plan or a
    view needs, such as the stage and the camera, as a device of its own.

A device declared with `service="stage_ioc"` gets that service's prefix as
its `prefix` argument, and the prefix is all it knows of the service. So you
can change one side and keep the other:

- The same components run against the lab's services or simulated ones; only
  the services change:

    ```yaml
    # common.yaml: what the setup is
    devices:
      stage:
        plugin_name: mylab
        plugin_id: stage
        service: stage_ioc
    ```

    ```yaml
    # lab.yaml: how it is reached in the lab
    services:
      stage_ioc:
        plugin_name: mylab
        plugin_id: stage-ioc
        prefix: "ST:"
    ```

    ```yaml
    # simulation.yaml: how it is reached without hardware
    services:
      stage_ioc:
        plugin_name: mylab
        plugin_id: stage-sim
        prefix: "ST:"
    ```

    The session lists `common.yaml` and one of the other two in its `config`.

- A crashing vendor library takes down its service, not the session; the
  service's devices time out until it is back.
- An [attached service](glossary.md#attached-service) can run on another
  machine, since the devices need only its prefix.

A device that needs no hardware, such as the soft stage in the
[tutorial](../tutorials/first-session.md), needs no service.

## Two connection levels

A device reaches its hardware in two steps, and each step connects on its own:

```d2 title="The two connection levels"
...@diagrams/style
label: "A device reaches its hardware in two levels, and each one connects on its own."
grid-columns: 2
horizontal-gap: 160
app: "session process" {
  view: {class: step}
  presenter: {class: step}
  device: {class: step}
  view -> presenter -> device
}
svc: "service process\nor container" {
  class: hidden
  ioc: "service" {class: [process; hidden]}
  hw: "hardware" {class: [hardware; hidden]}
  ioc -> hw: "2. open / close" {class: hidden}
}
app.device -> svc.ioc: "1. connect()" {class: hidden}
steps: {
  1: {
    label: "Level 1: the build calls connect() on every device declared with autoconnect, all at once. A device that hasn't connected after 10 seconds is left out."
    svc.class: step
    svc.ioc.class: process
    app.device: {
      class: current
      tooltip: The build calls connect() on every device declared with autoconnect, all at once. A device that hasn't connected after 10 seconds is left out, like one that fails to build.
    }
    (app.device -> svc.ioc)[0].style.opacity: 1
  }
  2: {
    label: "Level 2: the service opens the hardware its process variables name, such as a serial port or a camera, on the machine it runs on."
    app.device.class: step
    svc.hw.class: hardware
    svc.ioc: {
      class: [process; current]
      tooltip: The service opens a serial port or a camera. Which one it opens is set through its process variables.
    }
    svc.(ioc -> hw)[0].style.opacity: 1
  }
}
```

A [mocked session](glossary.md#mocked-session) connects each device to a
simulated backend and launches no service, so it reaches neither level. The
two levels are kept apart on purpose: a session can stay connected to a
service that holds no hardware yet, and a service can release its hardware
while every connection stays up.

## Launched and attached

A service is either [launched](glossary.md#launched-service) by the session or
attached to it. You declare a launched one with `Launch`, naming the module
the session runs, and an attached one with `Attach`, naming only its prefix:

```python
class MyApp(QtSession):
    camera_ioc: Annotated[
        AsService, Launch("mylab.iocs.camera", ready="Server startup complete.")
    ]
    beamline: Annotated[AsService, Attach("BL01:", address="10.0.0.5")]
```

An attached service already runs, in a container or on another host; the
session only passes its prefix on, and `address` says where to look when the
network search wouldn't find it. Either kind can also be declared in a session
file's `services` section, which fills any keyword the class leaves out; see
[Write a service](../how-to/write-a-service.md).

A launched service starts in the first build step, before any device:

```d2 title="Starting a launched service"
...@diagrams/style
shape: sequence_diagram
session: session
service: "service process"
devices: devices
session -> service: "python -m mylab.iocs.camera"
service -> session: "prints the ready line,\nwithin 15 s"
session -> devices: "build, each with its\nservice's prefix"
devices -> service: "connect()"
```

All launched services start at once, each waited for up to
[`STARTUP_TIMEOUT`][redsun.services.STARTUP_TIMEOUT]; one declared without
`ready` text counts as ready when its process starts. A service that doesn't
start is logged, and every device naming it is skipped. Services stop at
shutdown, after every component and before the log files close, so the files
record how each ended; a build that raises stops the ones it started.

## Stopping a process

The session asks a service to stop more and more firmly. After each step it
waits up to `stop_timeout` seconds, 10 unless the declaration gives another,
for the service to exit:

```d2 title="How the session stops a service"
...@diagrams/style
label: "The session asks a service to stop more and more firmly, waiting stop_timeout seconds, 10 unless the declaration says otherwise, after each request."
direction: right
stdin: "close its\nstandard input" {class: step}
sigint: "send SIGINT" {class: step}
kill: "kill it" {class: step}
stdin -> sigint: "still running,\non POSIX"
sigint -> kill: "still running"
stdin -> kill: "still running,\non Windows"
scenarios: {
  stdin: {
    label: "First it closes the service's standard input. A service that watches its input cleans up and exits, on every platform."
    stdin: {
      class: current
      tooltip: A service watching its standard input cleans up and exits.
    }
    sigint.style.opacity: 0.3
    kill.style.opacity: 0.3
  }
  sigint: {
    label: "On POSIX, a service still running then gets SIGINT."
    sigint: {
      class: current
      tooltip: Only on POSIX. On Windows, the session kills a service still running after the first step.
    }
    stdin.style.opacity: 0.3
    kill.style.opacity: 0.3
  }
  kill: {
    label: "A service still running after that, or on Windows after the first request, is killed, and may leave work such as a large file unfinished."
    kill: {
      class: current
      tooltip: A killed service may leave work unfinished, typically a large file it was writing.
    }
    stdin.style.opacity: 0.3
    sigint.style.opacity: 0.3
  }
}
```

Closing standard input comes first because it is the only request that runs a
service's cleanup on every platform: `Popen.terminate()` skips cleanup on
Windows and Linux, and a console control event never reaches a process
started without a console window, as a Qt application starts its services. It
also stops a service when the session crashes, since the operating system
closes the pipe. A service that needs longer to close takes a longer
`stop_timeout`.

## One transport per session

All the services of a session are reached over the same protocol, which you
name once in the `services` section of the configuration:

```yaml
services:
  transport: pv-access
  camera_ioc:
    plugin_name: mylab
    plugin_id: camera-ioc
```

A session speaks `channel-access` unless it says otherwise, and a file layered
over another can't change it. Pick a scenario to compare how each transport
sets up the launched services:

```d2 title="What the transport sets up"
...@diagrams/style
label: "The transport, named once in the services section, decides how the session sets up each launched service."
direction: right
session: "session process" {class: step}
camera: "camera_ioc" {class: process}
stage: "stage_ioc" {class: process}
session -> camera: "looks at\n127.0.0.1:5101"
session -> stage: "looks at\n127.0.0.1:5102"
scenarios: {
  channel-access: {
    label: "Channel Access: each launched service gets a server port of its own, and the session adds each port to its own process's address list."
    camera.label: "camera_ioc\nown port 5101"
    stage.label: "stage_ioc\nown port 5102"
    session.tooltip: The session gives each launched service a server port of its own, and adds each port to the address list of its own process.
  }
  pv-access: {
    label: "PVAccess: each launched service binds 127.0.0.1 on any free port, and the session tells its own process to search 127.0.0.1."
    camera.label: "camera_ioc\n127.0.0.1, free port"
    stage.label: "stage_ioc\n127.0.0.1, free port"
    (session -> camera)[0].label: "looks at\n127.0.0.1"
    (session -> stage)[0].label: "looks at\n127.0.0.1"
    session.tooltip: The session binds each launched service to 127.0.0.1 and lets it take any free port, and tells its own process to look at 127.0.0.1.
  }
}
```

The port numbers are examples: the session takes free ones.
[Environment variables](../reference/environment.md) lists what it sets.

There is one transport because both protocols read variables that hold one
setting for the whole process. Channel Access services get a port each
because of Windows, where a second IOC on the default port is never found:
libca reads its list of server addresses once per process, so each service
keeps its port for as long as the session process runs. PVAccess servers
share the search port, and the client is told to look at `127.0.0.1` because
it doesn't search the loopback address otherwise.

!!! warning "Another program can take the port first"

    A port is free when the session chooses it, but nothing holds it until
    the service binds it, so another program on the host can take it in
    between. If that happens, the service fails to start or its devices don't
    connect. The service keeps its port for the life of the session process,
    so to get a different port, start the session again in a new process.

`redsun` itself depends on `ophyd-async` and on nothing that either protocol
needs. Each component brings what its own service speaks, such as `caproto`,
`p4p` or `fastcs`, plus `ophyd-async[ca]` or `ophyd-async[pva]` for the device
side; see [Write a service](../how-to/write-a-service.md).

## What a launched service receives

A launched service is told its name and prefix, its ready text and the
session's log level, on top of the transport's variables. A Python service
reads them with [`identity`][redsun.services.identity],
[`ready`][redsun.services.ready] and
[`configure_logging`][redsun.services.configure_logging], so one module can
serve several sessions and name its channels from its identity.
[Environment variables](../reference/environment.md) lists how they are
passed.

## Unexpected exits

Nothing restarts a launched service that stops on its own. Step through what
happens instead:

```d2 title="A launched service exits on its own"
...@diagrams/style
label: "camera_ioc runs, and the camera's devices read and write through it."
direction: down
devices: "camera devices\nanswer" {
  class: step
  width: 220
}
service: "camera_ioc\nrunning" {class: process}
log: "ERROR in the log" {class: hidden}
signal: "sig_exited\n(name, code)" {class: hidden}
view: "view slot\nmain thread" {class: hidden}
presenter: "presenter slot\nthread service-camera_ioc" {class: hidden}
devices -> service: "reads, writes"
service -> log: {class: hidden}
service -> signal: {class: hidden}
signal -> view: {class: hidden}
signal -> presenter: {class: hidden}
steps: {
  1: {
    label: "camera_ioc exits on its own, after it was ready and without the session asking it to stop."
    service: "camera_ioc\nexited" {class: failed}
  }
  2: {
    label: "The session logs the exit code with the last 20 lines the service printed, and emits sig_exited with the service's name and code."
    log: {
      class: current
      tooltip: The session logs the exit code and the last 20 lines the service printed.
    }
    signal.class: current
    (service -> log)[0].style.opacity: 1
    (service -> signal)[0].style.opacity: 1
  }
  3: {
    label: "Connected slots run: a view's on the main thread in a Qt session, a presenter's on the thread that read the service's output unless it names another."
    log.class: step
    signal.class: step
    view: {
      class: current
      tooltip: In a Qt session, the slots of a view that is a widget run on the main thread.
    }
    presenter: {
      class: current
      tooltip: A presenter slot runs on the thread that read the service's output, unless you choose another thread for it.
    }
    (signal -> view)[0].style.opacity: 1
    (signal -> presenter)[0].style.opacity: 1
  }
  4: {
    label: "Nothing restarts the service, so every read or write of its devices times out after 10 seconds."
    view.class: step
    presenter.class: step
    devices: {
      class: failed
      label: "camera devices\nTimeoutError after 10 s"
    }
  }
  5: {
    label: "Once you start the service again, its devices answer again: both protocols reconnect on their own."
    service: "camera_ioc\nstarted again" {class: process}
    devices: {
      class: step
      label: "camera devices\nanswer again"
      tooltip: Both protocols reconnect on their own, so the devices need no reconnect.
    }
  }
}
```

[`sig_exited`][redsun.services.Service.sig_exited] is emitted only when the
service exits after it was ready and without being asked to stop, from the
thread reading its output, `service-<name>`. A
[presenter](glossary.md#presenter) [slot](glossary.md#slot) that touches what
only the main thread may use, such as a Qt widget, needs
`@slot(thread="main")`. An attached service has no process to watch, so an
outage shows up only as timeouts on its devices.

## Service output

Everything a launched service prints ends up in the logs, under the logger
`redsun.service.<name>` and in the service's own log file, next to the
application's:

```d2 title="Where a line of service output goes"
...@diagrams/style
direction: right
line: "a line the\nservice prints" {class: step}
json: "JSON log record\nkeeps its level and time" {
  class: step
  tooltip: A record written by loguru with serialize=True, or an object with the fields of a logging.LogRecord. It keeps its traceback, and its logger name under the service's logger.
}
pvxs: "pvxs line\nkeeps its level and time" {
  class: step
  tooltip: The text pvxs, the library under a PVAccess server, writes: a time, a level, a logger and a message.
}
other: "any other line\nlogged at DEBUG" {
  class: step
  tooltip: Such as a print, logged under the service's logger.
}
file: "the service's\nlog file" {class: file}
line -> json
line -> pvxs
line -> other
json -> file
pvxs -> file
other -> file
```

[Log from a service](../how-to/configure-logging.md#log-from-a-service) shows
how a service writes records the session can read.

## Not supported yet

- Restarting a crashed service.
- Standby, a service releasing its hardware while it stays connected. For now
  the presenter that owns the devices does it, see
  [Standby](components.md#standby); the session will take it over once
  `ophyd-async` can disconnect a device.
- Launching a service in a container. An attached service covers one you start
  beside the session with `docker compose`.

[ADR 12](decisions/0012-services-and-two-connection-levels.md) records the
decisions behind this design.
