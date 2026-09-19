# Devices

A device is the interface to a piece of hardware.

`redsun` leaves the device layer to
[ophyd-async](https://bluesky.github.io/ophyd-async/): device classes come
straight from `ophyd_async.core`.

```python
from ophyd_async.core import Device, StandardReadable, SignalRW, soft_signal_rw
```

## Choosing a base class

`ophyd-async` has a base class for each kind of device:

| Base class | Use when |
|------------|----------|
| `Device` | bare async device with no built-in read/describe logic |
| `StandardReadable` | readable device that composes signals into `read()` / `describe()` automatically |
| `StandardDetector` | detector composed from trigger/acquire/data logic, with a built-in prepare/kickoff/complete/collect lifecycle |
| `StandardFlyer` | flyer device that runs asynchronously and emits data at completion |
| `DeviceMap` | a `Device` holding string-keyed child devices (e.g. motor axes) |

Start from `StandardReadable` for most simple devices.

## Constructing a device in a container

A container builds a device as `cls(name=<component name>, **kwargs)`, with
the keyword arguments from the declaration and the configuration file. The
constructor must accept `name` by keyword, as every `ophyd-async` base class
does, so a device whose first parameter is something else builds too:

```python
from ophyd_async.epics.core import EpicsDevice

from redsun.containers import AppContainer, declare_device


class MyCamera(EpicsDevice): ...


class MyApp(AppContainer):
    camera = declare_device(MyCamera, prefix="CAM:")
```

A constructor taking `name` positional-only (`def __init__(self, name: str, /)`)
fails to build; the container logs it and skips the device.

## Connecting

After building the devices and before building the presenters, the build
connects every device at once, so a presenter reading a device while it is
built reads a connected one. A device that does not connect within ten seconds
is logged and skipped like one that fails to build: no presenter receives it,
and the build summary lists it as `camera (device, not connected)`. If the
device talks to a service, the message names the service.

A device declared with `autoconnect=False` (`autoconnect: false` in a
configuration file) is left unconnected. The application connects it when it
chooses, usually from a presenter a view reaches through the wiring:

```python
from psygnal import Signal

from redsun.presenter import Presenter
from redsun.virtual import slot


class StagePresenter(Presenter):
    sig_connected = Signal(str)

    @slot
    async def connect_stage(self) -> None:
        stage = self.devices["stage"]
        await stage.connect()
        self.sig_connected.emit(stage.name)
```

Such a presenter must not read the device before connecting it. `connect()` on
a connected device returns at once; `force_reconnect=True` connects it again.
[`connect_devices`][redsun.containers.container.AppContainer.connect_devices]
connects every device whatever its `autoconnect`, and
`connect_devices(mock=True)` connects them to mock backends for tests.

!!! note

    libca, the Channel Access client library, reads its list of addresses to
    search once per process, the first time the process uses Channel Access.
    A container launching its services before that works, and a container
    built again keeps each service on its port. A second container launching
    services under *other* names in the same process gives them ports the list
    lacks, and on Windows their devices do not connect.

## Signals

Signals are a device's typed, named attributes. `ophyd-async` has four signal types:

| Signal type | `bluesky` protocols | Description |
|-------------|-------------------|-------------|
| `SignalR[T]` | `Readable[T]`, `Subscribable[T]` | read-only |
| `SignalW[T]` | `HasName`, `Movable[T]` | write-only |
| `SignalRW[T]` | `Readable[T]`, `Subscribable[T]`, `Movable[T]` | read-write |
| `SignalX` | `HasName`, `Triggerable` | trigger / execute |

### Soft signals

Soft signals keep their value in memory, for simulation and tests.
`soft_signal_rw` creates a read-write soft signal, and
`soft_signal_r_and_setter` a read-only signal with a setter for code:

```python
from ophyd_async.core import StandardReadable, soft_signal_rw


class MyStage(StandardReadable):
    def __init__(self, name: str) -> None:
        self.position = soft_signal_rw(float, initial_value=0.0, units="mm")
        self.velocity = soft_signal_rw(float, initial_value=1.0, units="mm/s")
        super().__init__(name)
```

`StandardReadable` includes signals assigned before `super().__init__()` in
`read()` and `describe()`.

### Standalone signals

A signal is readable by `bluesky` on its own and can go straight into a plan
without its parent device:

```python
import bluesky.plans as bp

stage = MyStage("stage")
RE(bp.count([stage.position]))  # read only the position signal
RE(bp.count([stage]))  # read all signals registered by StandardReadable
```

## Detectors

A `StandardDetector` is composed from three logic classes, one concern each:

| Logic class | Concern |
|---|---|
| `DetectorTriggerLogic` | trigger configuration: `prepare_internal` / `prepare_edge` / `prepare_level`, deadtime |
| `DetectorAcquireLogic` | acquisition lifecycle: `ensure_ready` (stage), `start_acquiring` (kickoff/trigger), `wait_for_idle`, `ensure_stopped` (unstage) |
| `DetectorDataLogic` | data handling: `prepare_unbounded` / `prepare_single` return the data providers `complete()` and `collect()` operate on |

```python
from ophyd_async.core import StandardDetector

det = StandardDetector.__new__(StandardDetector)
det.add_detector_logics(trigger_logic, acquire_logic, data_logic)
StandardDetector.__init__(det, name="det")
```

### Writing acquired data

A device owns what it writes. Its service or `ophyd-async` writer chooses the
format, dimensions, chunking and when a file is complete; the device emits
`StreamResource` and `StreamDatum` documents with a `mimetype` matching the
bytes and `parameters["path"]` naming the array in the store. `redsun` writes
no acquisition bytes.

A device whose constructor takes `path_provider` receives the session's
[`SessionPathProvider`][redsun.path_provider.SessionPathProvider], an
`ophyd-async` `PathProvider` giving
`<base_dir>/<session>/<YYYY-MM-DD>/<datakey>/<plan>_<counter>`:

```python
class Camera(Device):
    def __init__(self, name: str, path_provider: PathProvider) -> None:
        super().__init__(name=name)
        self._path_provider = path_provider
```

Each data key gets its own directory and counter. A declaration cannot give
`path_provider` itself; a device not taking it picks its own paths. Details:
[the session's path provider](presenters.md#the-sessions-path-provider).

## Standby

A service holding hardware, such as a serial port or a camera, can release it
while it keeps running and take it back later, if it exposes a command for
each. The application triggers those commands, from the presenter owning the
devices:

```python
import asyncio
from typing import Annotated as A

from ophyd_async.core import TriggerableCommand
from ophyd_async.epics.core import EpicsDevice, PvSuffix

from redsun.presenter import Presenter
from redsun.virtual import slot


class MyCamera(EpicsDevice):
    open_camera: A[TriggerableCommand, PvSuffix("Open")]
    close_camera: A[TriggerableCommand, PvSuffix("Close")]


class HardwarePresenter(Presenter):
    @slot
    async def standby(self) -> None:
        await asyncio.gather(
            *(
                device.close_camera.trigger()
                for device in self.devices.values()
                if isinstance(device, MyCamera)
            )
        )
```

The devices stay connected and the service keeps running; the service decides
what releasing its hardware means.
