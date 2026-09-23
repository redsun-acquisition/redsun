# Write a service

Write a `caproto` IOC for a session to launch, declare it, and point a device
at it. [Services](../explanation/services.md) explains what a
[service](../reference/glossary.md#service) is and how a session handles it.

## Prerequisites

`redsun` depends on `ophyd-async` and on nothing a control-system protocol
needs, so a service brings its own. For a `caproto` IOC reached over Channel
Access:

```bash
uv add caproto "ophyd-async[ca]"
```

For one reached over PVAccess, use `p4p` or a library built on it, such as
`fastcs`, and `ophyd-async[pva]` for the device side.

## Write the IOC

Besides serving its process variables, a service that `redsun` launches must
print a line when it is ready, stop when its standard input closes, and listen
only on the local machine:

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

- `caproto` prints `Server startup complete.` once it serves. The session
  waits for that line.
- Closing standard input is how a session asks a service to stop, on every
  platform. The watcher raises `SIGINT`, so the service shuts down as it would
  on Ctrl+C. Use a daemon thread for it.
- If the session crashes, nobody reads the service's output any more, and
  printing raises. Clean up before printing, or do not print.
- `127.0.0.1` keeps a local service off the network. A service other machines
  must reach leaves `interfaces` alone.

## Declare it

In the session class, beside the device that talks to it:

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
            args=["--prefix", "CAM:"],
            stop_timeout=30,
        ),
    ]
    beamline: Annotated[AsService, Attach("BL01:")]
    camera: Annotated[AsDevice[MyCamera], Declare(service="camera_ioc")]
```

`Launch` is a service the session starts and stops. `Attach` is one already
running elsewhere: nothing starts or stops, and its devices only get its
prefix.

The device gets the service's prefix as its `prefix` argument, so giving the
device a `prefix` of its own is refused. A device whose service did not start
is left out.

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

Every service of a session speaks one [transport](../reference/glossary.md#transport),
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
configuration is read.
[Services](../explanation/services.md#one-transport-per-session) says what a
session does for each transport.

A launched process also reads its name and prefix from its environment, so a
module serving several sessions needs no arguments for them:

```python
prefix = os.environ.get("REDSUN_SERVICE_PREFIX", "")
name = os.environ.get("REDSUN_SERVICE_NAME", "")
```

## React when it exits

A launched service that exits by itself sends `sig_exited` with its name and
exit code. A service is set on the session under its name, so `wire` can
connect it:

```python
from redsun import AsPresenter, slot
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

    def wire(self) -> None:
        self.connect(self.camera_ioc.sig_exited, self.presenter.on_service_exited)
```

Without `thread="main"`, a presenter's slot runs on the thread reading the
service's output.

## Log from it

The service's output is logged under `redsun.service.<name>`, and written to
a log file of its own. To keep each record's level instead of logging every
line at `DEBUG`, print JSON; see
[Log from a service](configure-logging.md#log-from-a-service).
