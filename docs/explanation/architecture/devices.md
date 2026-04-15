# Devices

A `Device` class represents an interface with a hardware device.

`redsun` delegates the device layer entirely to [ophyd-async](https://bluesky.github.io/ophyd-async/).
The `redsun.device` module is a re-export namespace — all device primitives are imported from
`ophyd_async.core` and re-exported so that application code never needs to import from
`ophyd_async` directly.

```python
from redsun.device import Device, StandardReadable, SignalRW, soft_signal_rw
```

## Choosing a base class

ophyd-async provides several base classes depending on the complexity of your device:

| Base class | Use when |
|------------|----------|
| [`Device`][redsun.device.Device] | bare async device with no built-in read/describe logic |
| [`StandardReadable`][redsun.device.StandardReadable] | readable device that composes signals into `read()` / `describe()` automatically |
| [`StandardDetector`][redsun.device.StandardDetector] | detector with a controller/writer split and a built-in trigger/acquire/collect lifecycle |
| [`StandardFlyer`][redsun.device.StandardFlyer] | flyer device that runs asynchronously and emits data at completion |

For most simple devices, [`StandardReadable`][redsun.device.StandardReadable] is the right starting point.

## Signals

Signals are the typed, named attributes of a device. ophyd-async provides four signal types:

| Signal type | bluesky protocols | Description |
|-------------|-------------------|-------------|
| [`SignalR[T]`][redsun.device.SignalR] | `Readable[T]`, `Subscribable[T]` | read-only |
| [`SignalW[T]`][redsun.device.SignalW] | `HasName`, `Movable[T]` | write-only |
| [`SignalRW[T]`][redsun.device.SignalRW] | `Readable[T]`, `Subscribable[T]`, `Movable[T]` | read-write |
| [`SignalX`][redsun.device.SignalX] | `HasName`, `Triggerable` | trigger / execute |

### Soft signals

For simulation and testing, soft signals hold their value in memory.
Use [`soft_signal_rw`][redsun.device.soft_signal_rw] to create a read-write soft signal and
[`soft_signal_r_and_setter`][redsun.device.soft_signal_r_and_setter] to create a read-only signal
paired with a programmatic setter:

```python
from redsun.device import StandardReadable, soft_signal_rw

class MyStage(StandardReadable):
    def __init__(self, name: str) -> None:
        self.position = soft_signal_rw(float, initial_value=0.0, units="mm")
        self.velocity = soft_signal_rw(float, initial_value=1.0, units="mm/s")
        super().__init__(name)
```

Signals added before the `super().__init__()` call are automatically picked up by
`StandardReadable` and included in `read()` / `describe()`.

### Standalone signals

Each signal is itself a bluesky-readable object and can be passed directly to a plan
without going through its parent device:

```python
import bluesky.plans as bp

stage = MyStage("stage")
RE(bp.count([stage.position]))  # read only the position signal
RE(bp.count([stage]))           # read all signals registered by StandardReadable
```

## Detectors

[`StandardDetector`][redsun.device.StandardDetector] separates hardware control from data writing
through the [`DetectorController`][redsun.device.DetectorController] and
[`DetectorWriter`][redsun.device.DetectorWriter] protocols:

```python
from redsun.device import (
    StandardDetector,
    DetectorController,
    DetectorWriter,
    TriggerInfo,
    DetectorTrigger,
)

class MyController(DetectorController):
    async def prepare(self, trigger_info: TriggerInfo) -> None: ...
    async def arm(self) -> None: ...
    async def disarm(self) -> None: ...
    async def wait_for_idle(self) -> None: ...

    @property
    def trigger_types(self) -> tuple[DetectorTrigger, ...]: ...

class MyDetector(StandardDetector):
    def __init__(self, name: str) -> None:
        super().__init__(
            controller=MyController(),
            writer=MyWriter(),
            name=name,
        )
```

## Connecting devices

ophyd-async devices must be connected before use — this initialises their signal backends
and verifies hardware communication. Use
[`AppContainer.connect_devices()`][redsun.containers.container.AppContainer.connect_devices]
after calling [`build()`][redsun.containers.container.AppContainer.build]:

```python
app = MyApp()
app.build()
app.connect_devices()     # connects all registered devices
app.run()
```

Pass `mock=True` to skip hardware communication in tests:

```python
app.connect_devices(mock=True)
```

## redsun-specific protocols

The only redsun-specific protocol in the device layer is
[`HasCache`][redsun.device.HasCache], which expresses that a device can cache its most
recent reading for use in the presenter layer.
