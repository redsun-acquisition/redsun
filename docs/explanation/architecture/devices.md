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


## See Also

- [In-process devices](in-process-device.md)
