# Write a service

This guide writes a caproto IOC a session launches, declares it, and points a
device at it. For what a service is and how the container handles one, see
[Services](../explanation/services.md).

## Prerequisites

The `epics` extra, which brings caproto and ophyd-async's Channel Access
support:

```bash
uv add "redsun[epics]"
```

## Write the IOC

A service redsun launches does three things beyond serving its process
variables: it prints a line once it is ready, stops when its standard input
closes, and binds to the loopback interface.

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

- **The readiness line.** caproto prints `Server startup complete.` once it
  serves its process variables, and that is the line to wait for.
- **Standard input.** Closing it is how the container asks the service to stop
  on every platform. The watcher raises `SIGINT` so the service takes the path
  Ctrl+C takes, running caproto's shutdown hooks. It must be a daemon thread: a
  watcher run through `loop.run_in_executor` leaves the process waiting for a
  thread still blocked on the read.
- **Cleanup before output.** When the session that launched the service dies,
  the service sees its input close with nobody reading its output. Writing to
  standard output then raises, so do the cleanup first and print after it, or
  not at all.
- **Loopback.** Binding to `127.0.0.1` keeps a local service off the network. A
  service meant to be attached to from another machine leaves `interfaces`
  alone.

## Declare it

In Python, on the container, with the device that talks to it:

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

The device receives the service's prefix as its `prefix` keyword, so giving
`prefix` on the device as well is refused. A device naming a service that did
not start is skipped by the build.

In a plugin, the manifest names the module and the readiness line, and the
session file names the plugin entry:

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

`beamline` names no module, so it is attached to: nothing is started or
stopped, and its devices only receive its prefix.

## React when it exits

A launched service that exits unasked emits `sig_exited` with its name and exit
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

The service's output is logged under `redsun.service.<name>`. To keep its
records' levels rather than seeing every line at `DEBUG`, write them as JSON;
see [Log from a service](configure-logging.md#log-from-a-service).
