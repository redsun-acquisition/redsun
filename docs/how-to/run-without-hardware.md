---
icon: lucide/flask-conical
---

# How to run a session without hardware

Run a session as a [mocked session](../explanation/glossary.md#mocked-session):
its [devices](../explanation/glossary.md#device) connect to simulated
backends that `ophyd-async` provides, and no
[service](../explanation/glossary.md#service) is launched.
[Components](../explanation/components.md#connecting) explains how a session
connects its devices.

## Prerequisites

A session that builds with its hardware present, such as `MyApp` below. It
launches a service and points a device at it.

A mocked device still needs the package of its protocol installed: for the
signals below, `ophyd-async[ca]`:

```bash
uv add "ophyd-async[ca]"
```

The session:

```python
from typing import Annotated

from ophyd_async.core import StandardReadable
from ophyd_async.epics.core import epics_signal_r, epics_signal_rw

from redsun import AsDevice, AsService, Declare, Launch
from redsun.qt import QtSession


class MyMotor(StandardReadable):
    def __init__(self, name: str = "", *, prefix: str = "") -> None:
        with self.add_children_as_readables():
            self.readback = epics_signal_r(float, prefix + "Readback")
        self.setpoint = epics_signal_rw(float, prefix + "Setpoint")
        super().__init__(name=name)


class MyApp(QtSession):
    stage_ioc: Annotated[
        AsService,
        Launch("mylab.iocs.stage", ready="Server startup complete", prefix="STAGE:"),
    ]
    stage: Annotated[AsDevice[MyMotor], Declare(service="stage_ioc")]
```

## Set `mock`

Pass `mock` in the configuration the session is made with:

```python
MyApp({"mock": True}).run()
```

The mapping is layered over the configuration the class already has, so every
other key keeps its value. A session loaded from a file takes it the same way,
as the last of its sources:

```python
from redsun import Session

app = Session.from_config(["session.yaml", {"mock": True}]).build()
```

To mock every run of a session instead, write the key in its
[session file](../explanation/glossary.md#session-file):

```yaml
mock: true
```

## Check the log

The build logs one line in place of starting the services, then the usual
summary:

```text
[29-09-26|08:43:21][INFO]: Services not started: the session is mocked
[29-09-26|08:43:21][INFO]: Session built: 1/1 devices, 0/0 presenters, 0/0 views
```

Every device the build connects is on a simulated backend, including one
declared with `service=`: it still gets the service's prefix, but nothing
answers on it. A signal of a mocked device keeps the last value written to
it, and starts at the default of its type, `0.0` for a `float`.

A session keeping a [catalog](keep-a-catalog.md) starts it as usual, since
the catalog reaches no hardware, and records the runs of the mocked devices.

A device declared with `autoconnect=False` is not connected by the build; see
[How to connect a device on demand](connect-a-device-on-demand.md).

## Give a mocked device its values

Set its signals from a component that only a mocked session declares, with
[`set_mock_value`][ophyd_async.core.set_mock_value]. It works on signals the
device only reads, such as a readback, and
[`callback_on_mock_put`][ophyd_async.core.callback_on_mock_put] has the
readback follow each value written to the setpoint:

```python
from typing import Any, ClassVar

from ophyd_async.core import callback_on_mock_put, set_mock_value

from redsun import AsPresenter, DeviceMapping


class SimulatedStage:
    def __init__(self, name: str, *, devices: DeviceMapping) -> None:
        self.name = name
        stage = devices["stage"]
        assert isinstance(stage, MyMotor)
        set_mock_value(stage.readback, 2.5)
        callback_on_mock_put(
            stage.setpoint, lambda value: set_mock_value(stage.readback, value)
        )


class MySimulation(MyApp):
    config: ClassVar[dict[str, Any]] = {"mock": True}
    simulation: AsPresenter[SimulatedStage]
```

Run `MySimulation().run()` to open the window: a view of `MyApp` that shows
the stage reads those values. Presenters
are built after the devices connect, so the values are in place before any
view shows them. Both functions raise on a device not connected with
`mock=True`, so keep `SimulatedStage` out of `MyApp`.

## Go back to the hardware

Remove `mock` from the configuration, or set it to `false`. The next build
starts the services and connects the devices to them.
