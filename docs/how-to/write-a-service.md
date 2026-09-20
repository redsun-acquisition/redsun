# Write a service

Write a `caproto` IOC for a session to launch, declare it, and point a device
at it. [Services](../explanation/services.md) explains what a service is and
how the container handles it.

## Prerequisites

`redsun` depends on `ophyd-async` and on nothing a control-system protocol
needs, so a service brings its own. For a `caproto` IOC reached over Channel
Access:

```bash
uv add caproto "ophyd-async[ca]"
```

For one reached over PVAccess, `p4p` or a library written on it, such as
`fastcs`, and `ophyd-async[pva]` for the device side.

## Write the IOC

Besides serving its process variables, a service `redsun` launches prints a
line when ready, stops when its standard input closes, and binds to the
loopback interface.

```python
# mylab/iocs/camera.py
import signal
import sys
import threading

from caproto.server import PVGroup, ioc_arg_parser, pvproperty, run


def stop_when_stdin_closes() -> None:
    sys.stdin.read()
    signal.raise_signal(signal.SIGINT)


class Camera(PVGroup):
    exposure = pvproperty(value=0.1, name="Exposure")


if __name__ == "__main__":
    options, run_options = ioc_arg_parser(default_prefix="CAM:", desc="camera")
    threading.Thread(target=stop_when_stdin_closes, daemon=True).start()
    run(Camera(**options).pvdb, **{**run_options, "interfaces": ["127.0.0.1"]})
```

- **The readiness line.** `caproto` prints `Server startup complete.` once it
  serves its process variables; wait for that line.
- **Standard input.** Closing it is how the container asks a service to stop on
  every platform. The watcher raises `SIGINT`, so the service shuts down as on
  Ctrl+C and runs `caproto`'s shutdown hooks. Use a daemon thread: a watcher run
  through `loop.run_in_executor` leaves the process waiting on a thread still
  blocked on the read.
- **Cleanup before output.** If the launching session dies, the service's input
  closes and nobody reads its output, so writing to standard output raises.
  Clean up first, then print, or do not print.
- **Loopback.** Binding to `127.0.0.1` keeps a local service off the network. A
  service other machines attach to leaves `interfaces` alone.

## Declare it

In Python, on the container, beside the device that talks to it:

```python
from redsun.containers import AppContainer, declare_device, declare_service


class MyApp(AppContainer):
    camera_ioc = declare_service(
        module="mylab.iocs.camera",
        ready="Server startup complete.",
        prefix="CAM:",
        args=["--prefix", "CAM:"],
        stop_timeout=30,
    )
    camera = declare_device(MyCamera, service="camera_ioc")
```

The device receives the service's prefix as its `prefix` keyword, so a device
also given `prefix` is refused. The build skips a device whose service did not
start.

In a plugin, the manifest gives the module and readiness line, and the session
file names the plugin entry:

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
    args: ["--prefix", "CAM:"]
  beamline:
    prefix: "BL01:"

devices:
  camera:
    plugin_name: mylab
    plugin_id: camera
    service: camera_ioc
```

`beamline` has no module, so it is attached to: nothing starts or stops, and
its devices only receive its prefix.

## Name the transport

Every service of a session is reached over one protocol, `channel-access`
unless the session says otherwise. A session file names it under `services`,
beside the services themselves:

```yaml
services:
  transport: pv-access
  camera_ioc:
    plugin_name: mylab
    plugin_id: camera-ioc
```

A container declaring its services in Python names it as an attribute:

```python
class MyApp(AppContainer):
    transport = "pv-access"

    camera_ioc = declare_service(
        module="mylab.iocs.camera", ready="serving", prefix="CAM:"
    )
```

A transport `redsun` does not have, a component named `transport`, and two
layered files naming different transports are each refused as the class is
created.
[Services](../explanation/services.md#one-transport-per-session) describes what
a session does for each of them.

The process is launched with two variables of its own, so a module serving
several sessions names its channels without taking arguments for them:

```python
prefix = os.environ.get("REDSUN_SERVICE_PREFIX", "")
name = os.environ.get("REDSUN_SERVICE_NAME", "")
```

## React when it exits

A launched service exiting unasked emits `sig_exited` with its name and exit
code. Connect it in `wire`:

```python
from redsun.containers import AppContainer, declare_presenter, declare_service
from redsun.log import Loggable
from redsun.presenter import Presenter
from redsun.virtual import slot


class CameraPresenter(Presenter, Loggable):
    @slot(thread="main")
    def on_service_exited(self, name: str, code: int) -> None:
        self.logger.warning(f"{name} exited with code {code}")


class MyApp(AppContainer):
    camera_ioc = declare_service(
        module="mylab.iocs.camera", ready="Server startup complete."
    )
    presenter = declare_presenter(CameraPresenter)

    def wire(self) -> None:
        self.connect(self.camera_ioc.sig_exited, self.presenter.on_service_exited)
```

Without `thread="main"`, a presenter slot runs on the thread reading the
service's output.

## Log from it

The service's output is logged under `redsun.service.<name>`. To keep record
levels instead of every line at `DEBUG`, write JSON; see
[Log from a service](configure-logging.md#log-from-a-service).
