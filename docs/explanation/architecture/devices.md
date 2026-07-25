# Devices

A device represents an interface with a hardware component.

`redsun` delegates the device layer entirely to
[ophyd-async](https://bluesky.github.io/ophyd-async/): device primitives are
imported directly from `ophyd_async.core`. The `redsun.device` module only
hosts redsun-specific device protocols (currently
[`HasAsyncShutdown`][redsun.device.protocols.HasAsyncShutdown]).

```python
from ophyd_async.core import Device, StandardReadable, SignalRW, soft_signal_rw
```

## Choosing a base class

ophyd-async provides several base classes depending on the complexity of your device:

| Base class | Use when |
|------------|----------|
| `Device` | bare async device with no built-in read/describe logic |
| `StandardReadable` | readable device that composes signals into `read()` / `describe()` automatically |
| `StandardDetector` | detector composed from trigger/acquire/data logic, with a built-in prepare/kickoff/complete/collect lifecycle |
| `StandardFlyer` | flyer device that runs asynchronously and emits data at completion |
| `DeviceMap` | a `Device` holding string-keyed child devices (e.g. motor axes) |

For most simple devices, `StandardReadable` is the right starting point.

## Signals

Signals are the typed, named attributes of a device. ophyd-async provides four signal types:

| Signal type | bluesky protocols | Description |
|-------------|-------------------|-------------|
| `SignalR[T]` | `Readable[T]`, `Subscribable[T]` | read-only |
| `SignalW[T]` | `HasName`, `Movable[T]` | write-only |
| `SignalRW[T]` | `Readable[T]`, `Subscribable[T]`, `Movable[T]` | read-write |
| `SignalX` | `HasName`, `Triggerable` | trigger / execute |

### Soft signals

For simulation and testing, soft signals hold their value in memory.
Use `soft_signal_rw` to create a read-write soft signal and
`soft_signal_r_and_setter` to create a read-only signal paired with a
programmatic setter:

```python
from ophyd_async.core import StandardReadable, soft_signal_rw


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
RE(bp.count([stage]))  # read all signals registered by StandardReadable
```

## Detectors

`StandardDetector` is assembled by **composition** from three logic classes,
each owning one concern:

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

Detector data logics meet redsun's storage layer through
[`BaseStorage`][redsun.storage.BaseStorage]: the trigger logic registers a
[`StreamSpec`][redsun.storage.StreamSpec] at prepare time, the data logic
obtains a [`FrameSink`][redsun.storage.FrameSink] and builds its
`StreamResourceDataProvider` from `uri_for` / `resource_info_for` /
`signal_for`, and the acquire logic pushes frames with `await sink.put(...)`
from kickoff onwards. Devices never see the path provider — only the
storage instance, resolved through the
[storage registry][redsun.storage.get_storage].

The full contract — including when to open eagerly versus lazily, and how a
live view streams frames without creating a store — is documented in
[Session storage](../storage.md) and
[ADR 0002](../decisions/0002-storage-dual-context-redesign.md). The
reference implementation of both patterns lives in
`tests/sdk/storage/test_integration_plans.py`.

## Connecting devices

ophyd-async devices must be connected before use — this initialises their signal backends
and verifies hardware communication. Use
[`AppContainer.connect_devices()`][redsun.containers.container.AppContainer.connect_devices]
after calling [`build()`][redsun.containers.container.AppContainer.build]:

```python
app = MyApp()
app.build()
app.connect_devices()  # connects all registered devices
app.run()
```

Pass `mock=True` to skip hardware communication in tests:

```python
app.connect_devices(mock=True)
```

## redsun-specific protocols

The only redsun-specific protocol in the device layer is
[`HasAsyncShutdown`][redsun.device.protocols.HasAsyncShutdown], which marks a
device as supporting an asynchronous shutdown at application teardown.
