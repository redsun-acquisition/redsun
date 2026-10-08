---
icon: lucide/server-cog
---

# How a session runs and talks to services

A service is a server your devices talk to, such as an
[EPICS](glossary.md#epics) [IOC](glossary.md#ioc), a camera server or a motion
controller's gateway. Your [`ophyd-async`](glossary.md#ophyd-async) devices
talk to it over [Channel Access](glossary.md#channel-access) or
[PVAccess](glossary.md#pvaccess), and `redsun` takes no part in that. `redsun`
handles everything around it: it starts the service when the session launches
it, notices when it exits, stops it cleanly, and gives its
[prefix](glossary.md#prefix) and transport to the devices that use it.

!!! warning "Devices without a service"

    You don't strictly need a service, since an `ophyd-async` device can
    reach its hardware on its own. For now, though, `redsun` supports such
    devices only in part, so a service is the preferred way to reach
    hardware. We will provide tutorials on wrapping third-party packages
    through `ophyd-async` in the future.

## Devices and services

A session splits your setup into devices and services, which know as little as
possible about each other. Step through the diagram, and point at a shape to
read what it does:

```d2 title="Devices meet services at the prefix"
...@diagrams/style
direction: down
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
  class: hidden
  stage_ioc: "stage service" {class: [process; hidden]}
  camera_ioc: "camera service" {class: [process; hidden]}
}
motors: "motor controller" {class: [hardware; hidden]}
sensor: "camera" {class: [hardware; hidden]}
model.stage -> impl.stage_ioc: "prefix ST:" {class: hidden}
model.camera -> impl.camera_ioc: "prefix CAM:" {class: hidden}
impl.stage_ioc -> motors: {class: hidden}
impl.camera_ioc -> sensor: {class: hidden}
steps: {
  1: {
    impl.class: step
    impl.stage_ioc: {
      class: process
      tooltip: A service opens the serial port or the camera, speaks the vendor's protocol or runs the vendor's library, and offers the result as process variables. It knows nothing about the setup around it.
    }
    impl.camera_ioc: {
      class: process
      tooltip: A service opens the serial port or the camera, speaks the vendor's protocol or runs the vendor's library, and offers the result as process variables. It knows nothing about the setup around it.
    }
    (model.stage -> impl.stage_ioc)[0].style.opacity: 1
    (model.camera -> impl.camera_ioc)[0].style.opacity: 1
  }
  2: {
    motors.class: hardware
    sensor.class: hardware
    (impl.stage_ioc -> motors)[0].style.opacity: 1
    (impl.camera_ioc -> sensor)[0].style.opacity: 1
  }
}
```

The devices are a model of your whole setup, written the way the people using
it think about it: a microscope has a stage, the stage has an X and a Y axis,
and each axis has a position. `ophyd-async` builds devices as a tree for this
reason, since a device can hold other devices as its children, down to the
signals. A service describes no setup at all. It only makes some piece of
hardware reachable, so the same model can sit on top of real hardware or of a
simulation.

!!! note "One device for the whole setup"

    We intend each setup to be described by a single device at the root of
    such a tree, such as a `MyMicroscope` that holds its stage and its camera.
    For now, some features of `redsun` look only at the devices a session
    declares and not at their children, so declare each piece a plan or a
    view needs, such as the stage and the camera, as a device of its own.

When you declare a device with `service="stage_ioc"`, the session passes it
that service's prefix as its `prefix` argument, and the prefix is all the
device knows about the service. Because neither side depends on the other, you
can change one and leave the other alone:

- You can run the same devices, presenters and views against the real
  services in the lab and against simulated ones on a laptop. Only the
  services change:

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

    Your session then lists `common.yaml` and one of the other two in its
    `config`.

- If a vendor library crashes, it takes down its service process, not the
  session. The session logs the exit, and the devices of that service time out
  until it is back.
- A service can lend its hardware to another program while every device stays
  connected, and take it back later. For now your application does this
  itself; see [Standby](components.md#standby).
- An [attached service](glossary.md#attached-service) runs wherever the
  hardware is plugged in, even on another machine, because the devices only
  need its prefix.

A device that needs no hardware at all, such as the soft stage in the
[tutorial](../tutorials/first-session.md), needs no service either.

## Two connection levels

A device reaches its hardware in two steps, and each step connects on its own:

```d2 title="The two connection levels"
...@diagrams/style
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
    svc.class: step
    svc.ioc.class: process
    app.device: {
      class: current
      tooltip: The build calls connect() on every device declared with autoconnect, all at once. A device that hasn't connected after 10 seconds is left out, like one that fails to build.
    }
    (app.device -> svc.ioc)[0].style.opacity: 1
  }
  2: {
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

The session connects the first level when it builds: it calls `ophyd-async`'s
`connect()` on every device declared with `autoconnect`, and skips a device
that doesn't connect, just like one that fails to build. A
[mocked session](glossary.md#mocked-session) connects each device to a
simulated backend and launches no service, so it reaches neither level.

The service connects the second level by opening the hardware its process
variables name. This works the same for a service on another machine, since
the list of ports comes from the machine that has them.

Keeping the two levels apart is deliberate: a session can stay connected to a
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

An attached service is already running, in a container or on another host, so
the session only passes its prefix on to the devices. An `address` tells the
session where to look when the network search wouldn't find it. You can
declare either kind on the session class or in the `services` section of a
session file, and any keyword the class leaves out is taken from the file. See
[Write a service](../how-to/write-a-service.md).

The session owns a launched service from start to stop. Starting is the first
build step, before any device is built:

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

The session starts every launched service at once and waits for each ready
line up to [`STARTUP_TIMEOUT`][redsun.services.STARTUP_TIMEOUT]. A service
declared without `ready` text counts as ready once its process starts. If a
service doesn't start, the session logs it and skips every device that names
it. A [mocked session](glossary.md#mocked-session) starts no service. Stopping
happens at shutdown, after every component and before the session's log files
close, so the files record how each service ended. If the build raises, it
stops the services it already started before the error leaves it.

## Stopping a process

The session asks a service to stop more and more firmly. After each step it
waits up to `stop_timeout` seconds, 10 unless the declaration gives another,
for the service to exit:

```d2 title="How the session stops a service"
...@diagrams/style
direction: right
stdin: "close its\nstandard input" {class: step}
sigint: "send SIGINT" {class: step}
kill: "kill it" {class: step}
stdin -> sigint: "still running,\non POSIX"
sigint -> kill: "still running"
stdin -> kill: "still running,\non Windows"
scenarios: {
  stdin: {
    stdin: {
      class: current
      tooltip: A service watching its standard input cleans up and exits.
    }
    sigint.style.opacity: 0.3
    kill.style.opacity: 0.3
  }
  sigint: {
    sigint: {
      class: current
      tooltip: Only on POSIX. On Windows, the session kills a service still running after the first step.
    }
    stdin.style.opacity: 0.3
    kill.style.opacity: 0.3
  }
  kill: {
    kill: {
      class: current
      tooltip: A killed service may leave work unfinished, typically a large file it was writing.
    }
    stdin.style.opacity: 0.3
    sigint.style.opacity: 0.3
  }
}
```

Closing standard input comes first because it's the only request that runs a
service's cleanup on every platform. `Popen.terminate()` skips cleanup on both
Windows and Linux, and a console control event never reaches a process started
without a console window. A Qt application has to start its services without
one, or each service opens its own window. Closing standard input also stops a
service when the session crashes, because the operating system closes the pipe
and the service reads the end of its input.

If your service needs longer to close, give it a longer `stop_timeout`.

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
over another can't change it. The transport decides how the session sets up
each launched service. Pick a scenario to compare the two:

```d2 title="What the transport sets up"
...@diagrams/style
direction: right
session: "session process" {class: step}
camera: "camera_ioc" {class: process}
stage: "stage_ioc" {class: process}
session -> camera: "looks at\n127.0.0.1:5101"
session -> stage: "looks at\n127.0.0.1:5102"
scenarios: {
  channel-access: {
    camera.label: "camera_ioc\nown port 5101"
    stage.label: "stage_ioc\nown port 5102"
    session.tooltip: The session gives each launched service a server port of its own, and adds each port to the address list of its own process.
  }
  pv-access: {
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

Only one transport is allowed because the variables both protocols read hold
one setting for the whole process. With two transports in one session, no
variable could say which service it is for.

Each launched Channel Access service gets its own port because of Windows. On
Linux, two IOCs on the default port both answer, but on Windows the second one
is never found. The cause is libca, the Channel Access client library, which
reads its list of server addresses only once per process. So each service
keeps its port for as long as the session process runs, and if you build the
session again in the same process, it finds the service on the same port.

PVAccess needs none of this: servers on one machine share the search port,
and the session asks each for port `0`, so it takes any free port. The session still
tells its own process to look at `127.0.0.1`, because a PVAccess client
doesn't search the loopback address unless it's told to.

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

When the session launches a service, it tells the service its name and
prefix, the ready text from its declaration, and the level the session logs
at, on top of the transport's variables. A Python service reads these through
the functions of `redsun.services`:
[`identity`][redsun.services.identity],
[`ready`][redsun.services.ready] and
[`configure_logging`][redsun.services.configure_logging].
[Environment variables](../reference/environment.md) lists how they are
passed.

Because a service learns its name this way, a module that serves several
sessions names its channels from its identity instead of taking arguments for
it.

## Unexpected exits

Nothing restarts a launched service that stops on its own. Step through what
happens instead:

```d2 title="A launched service exits on its own"
...@diagrams/style
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
    service: "camera_ioc\nexited" {class: failed}
  }
  2: {
    log: {
      class: current
      tooltip: The session logs the exit code and the last 20 lines the service printed.
    }
    signal.class: current
    (service -> log)[0].style.opacity: 1
    (service -> signal)[0].style.opacity: 1
  }
  3: {
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
    view.class: step
    presenter.class: step
    devices: {
      class: failed
      label: "camera devices\nTimeoutError after 10 s"
    }
  }
  5: {
    service: "camera_ioc\nstarted again" {class: process}
    devices: {
      class: step
      label: "camera devices\nanswer again"
      tooltip: Both protocols reconnect on their own, so the devices need no reconnect.
    }
  }
}
```

The service emits [`sig_exited`][redsun.services.Service.sig_exited] only when
it exits after it was ready and without being asked to stop. It's emitted from
the thread that reads the service's output, named `service-<name>`, so where a
[slot](glossary.md#slot) connected to it runs depends on the component that
owns the slot. A [view](glossary.md#view)'s slots run on the main thread in a
Qt session. A [presenter](glossary.md#presenter) slot runs on the output
thread unless you choose another thread for it. That thread has no more output
to read once the service has exited, so the slot running there gets in nobody's
way. If your presenter slot touches anything that only the main thread may
use, such as a Qt widget, declare it with `@slot(thread="main")`.

An attached service has no process for the session to watch, so an outage
shows up only as timeouts on its devices.

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

- **Restarting a crashed service.**
- **Standby**, a service releasing its hardware while it stays connected. For
  now your application writes it, in the presenter that owns the devices; see
  [Standby](components.md#standby). The session will take it over once
  `ophyd-async` can disconnect a device, and standby will then also be able to
  drop connections and stop launched services.
- **Launching a service in a container.** An attached service covers one you
  start beside the session with `docker compose`.

[ADR 12](decisions/0012-services-and-two-connection-levels.md) records the
decisions behind this design.
