# Devices

A `Device` class represents an interface with a hardware device.

The definition of a device is quite fluid, as there are many ways that it can interact with the hardware depending on your needs.

All devices must inherit from the [`Device`][redsun.device.Device] base class, either:

- directly, via inheritance;
- indirectly, following structural subtyping ([PEP 544](https://peps.python.org/pep-0544/)) via the [`PDevice`][redsun.device.PDevice] protocol.

Each device requires a positional-only argument `name` that serves as a unique identifier for a `redsun` session; additional initialization parameters can be provided as
keyword-only arguments.

```python

from redsun.device import Device

class MyDevice(Device)

    def __init__(self, name: str, /, int_param: int, str_param: str) -> None:
        ... # your implementation
```


## Attribute API and ophyd-async alignment

Redsun provides a set of structural protocols — [`AttrR`][redsun.device.AttrR], [`AttrRW`][redsun.device.AttrRW], [`AttrW`][redsun.device.AttrW], and [`AttrT`][redsun.device.AttrT] — designed to structurally match the signal types in [ophyd-async](https://bluesky.github.io/ophyd-async/). Because both sides are defined in terms of the same bluesky protocols, redsun attributes and ophyd-async signals satisfy the same structural contracts and can be used interchangeably in plans.

| redsun protocol | ophyd-async equivalent | bluesky protocols |
|-----------------|------------------------|-------------------|
| `AttrR[T]` | `SignalR[T]` | `Readable[T]`, `Subscribable[T]` |
| `AttrW[T]` | `SignalW[T]` | `HasName`, `Movable[T]` |
| `AttrRW[T]` | `SignalRW[T]` | `Readable[T]`, `Subscribable[T]`, `Movable[T]` |
| `AttrT` | `SignalX` | `HasName`, `Triggerable` |

[`SoftAttrR`][redsun.device.SoftAttrR], [`SoftAttrRW`][redsun.device.SoftAttrRW], and [`SoftAttrT`][redsun.device.SoftAttrT] are in-memory concrete implementations useful for simulation and testing.

### Standalone attributes

Each attribute is itself a bluesky-readable object and can be passed directly to a plan without going through its parent device:

```python
import bluesky.plans as bp

stage = MyStage("stage")
RE(bp.count([stage.position]))  # read only the position attribute
```

`Device.read_configuration()` and `describe_configuration()` return `{}` by default — the base class does not aggregate attributes automatically. To make a whole device readable, override `read()` and `describe()` to collect the attributes you need:

```python
from redsun.device import Device, SoftAttrRW

class MyStage(Device):
    def __init__(self, name: str, /) -> None:
        super().__init__(name)
        self.position = SoftAttrRW(f"{name}-position", initial_value=0.0, units="mm")
        self.velocity = SoftAttrRW(f"{name}-velocity", initial_value=1.0, units="mm/s")

    def read(self):
        return {**self.position.read(), **self.velocity.read()}

    def describe(self):
        return {**self.position.describe(), **self.velocity.describe()}


stage = MyStage("stage")

# Standalone — pass one attribute directly
RE(bp.count([stage.position]))

# Aggregated — pass the whole device once read/describe are overridden
RE(bp.count([stage]))
```

### ophyd-async device compatibility

Devices from ophyd-async can be registered in a redsun container directly.
[`StandardReadable`](https://bluesky.github.io/ophyd-async/main/reference/ophyd_async.core.html#ophyd_async.core.StandardReadable) and `StandardDetector` satisfy [`PDevice`][redsun.device.PDevice] structurally and require no adaptation.
Bare `ophyd_async.core.Device` does not satisfy `PDevice` because it does not implement `Configurable`; use `StandardReadable` or provide `read_configuration` / `describe_configuration` overrides.
