---
icon: lucide/plug
---

# How to connect a device on demand

Build a device without connecting it, and connect it from a component when
the user asks. [Connecting](../explanation/components.md#connecting) explains
what the build does with the other devices.

## Prerequisites

A session declaring the device, and a component that uses it.

## Declare the device unconnected

Give the declaration `autoconnect=False`:

```python
from typing import Annotated

from redsun import AsDevice, Declare
from redsun.qt import QtSession


class MyApp(QtSession):
    motor: Annotated[AsDevice[MyMotor], Declare(autoconnect=False)]
```

Or in the session file:

```yaml
devices:
  motor:
    plugin_name: mylab
    plugin_id: motor
    autoconnect: false
```

`autoconnect` takes `true` or `false` only. The session keeps it and does not
pass it to the constructor, so it cannot be given to a device class whose
constructor takes an `autoconnect` of its own.

The device is built, and is in `devices` like any other, but the build does
not connect it and does not leave it out when its hardware is missing.

## Connect it from a component

Ask for the devices and connect in an `async` slot:

```python
from ophyd_async.core import NotConnectedError
from psygnal import Signal

from redsun import DeviceMapping, slot


class MyController:
    sig_connected = Signal(str)
    sig_not_connected = Signal(str, str)

    def __init__(self, name: str, *, devices: DeviceMapping) -> None:
        self.name = name
        self.devices = devices

    @slot
    async def connect_motor(self) -> None:
        motor = self.devices["motor"]
        try:
            await motor.connect(timeout=5)
        except NotConnectedError as e:
            self.sig_not_connected.emit(motor.name, str(e))
            return
        self.sig_connected.emit(motor.name)
```

A [mocked session](../explanation/glossary.md#mocked-session) connects the
other devices to simulated backends, but does not tell a component it is
mocked. To connect this device to one, pass `mock=True` to `connect` yourself.

## Ask for it from a view

Link the view's signal to the slot, and the answers back:

```python
class MyApp(QtSession):
    motor: Annotated[AsDevice[MyMotor], Declare(autoconnect=False)]
    ctrl: AsPresenter[MyController]
    panel: AsView[MyView]

    def wire(self) -> Iterator[Link]:
        yield self.panel.sig_connect_clicked, self.ctrl.connect_motor
        yield self.ctrl.sig_connected, self.panel.on_connected
        yield self.ctrl.sig_not_connected, self.panel.on_not_connected
```

## Shut it down unconnected

The session calls the device's `shutdown` when it ends, whether or not a
component connected it. A `shutdown` that writes to the hardware has to cope
with a device that never connected.
