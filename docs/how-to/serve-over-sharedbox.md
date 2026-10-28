---
icon: lucide/memory-stick
---

# How to serve a FastCS controller over sharedbox

When a session and its [service](../explanation/glossary.md#service) run on
the same computer, they can exchange values through shared memory instead of a
network protocol. The `sharedbox`
[transport](../explanation/glossary.md#transport) serves a `fastcs` controller
as [boxes](../explanation/glossary.md#box), and the session builds an
[`ophyd-async`](../explanation/glossary.md#ophyd-async) device from them
without naming a single field. This page shows
the three pieces: the service, the device and the declaration.
[How to write a service](write-a-service.md) covers what every launched
service does, and this page builds on it.

## Prerequisites

Install `redsun` with the `sharedbox` extra, which brings `sharedbox` and
`fastcs`:

```bash
uv add "redsun[sharedbox]"
```

`sharedbox` runs on Windows x64 and Linux x86_64.

The service and the session have to run on the same computer, because a box
lives in that computer's memory. A service other machines must reach needs
one of the network transports.

!!! note "Written for `fastcs` 0.14"

    The API of `fastcs` is still changing, and this page follows it. If a
    name on this page no longer exists in the version you installed, check
    the documentation of `fastcs`.

## Write the service

Describe the hardware as a `fastcs` controller. This one has an exposure the
session can set, a state it can read and a command it can run:

```{.python}
--8<-- "docs/examples/box_service.py:controller"
```

Then serve it with [`serve_controller`][redsun.services.serve_controller] and a
[`BoxTransport`][redsun.services.sharedbox.BoxTransport]:

```{.python}
--8<-- "docs/examples/box_service.py:serve"
```

- `serve_controller` serves the controller under the
  [prefix](../explanation/glossary.md#prefix) the session gave the process, and
  stops when the session asks. Run alone, the service has no session, so it
  passes `MYAPP:DET` instead.
- Once the boxes exist, it prints the `ready` text the declaration gives, so
  the session never connects a device before the service serves.
- [`configure_logging`][redsun.services.configure_logging] sends the records
  of `fastcs` to the session, as on the other transports.

`BoxTransport` gives the controller a box, and each of its sub-controllers a
box of its own. It then publishes one more box under the prefix, the index,
which lists every box and the attributes and commands in it. The session
learns the layout from the index, so a controller whose attributes are read
from the hardware in `initialise` works without any change.

## Point a device at it

Declare the signals and commands the session needs, and give the device a
[`BoxDeviceConnector`][redsun.device.sharedbox.BoxDeviceConnector] with the
prefix:

```{.python}
--8<-- "docs/examples/box_detector.py:device"
```

When the device connects, the connector reads the index and fills in every
attribute, command and sub-controller the service serves, declared or not. It
then checks the ones you declared, so `connect` fails with the name of a
declared child the service doesn't serve, or one whose type differs from what
the service serves. A `fastcs` `ControllerVector`, a numbered list of
sub-controllers, becomes an `ophyd-async` `DeviceVector`, its numbered list of
sub-devices. A `fastcs` command becomes a `TriggerableCommand`.

The values of a declared enum must be the names of the members of the `fastcs`
enum, since an enum travels by name.

## Declare it

Name the transport in the session's configuration, and declare the service
beside the device:

```{.python}
--8<-- "docs/examples/box_detector.py:session"
```

In a session file the transport goes in the `services` section, as for the
other transports:

```yaml
services:
  transport: sharedbox
  detector_service:
    module: box_service
    ready: "detector ready"
    prefix: "MYAPP:DET"
```

A trailing colon makes no difference: `MYAPP:DET:` and `MYAPP:DET` name the
same boxes. The prefix holds letters, digits, `_` and `-`, in parts separated
by colons.

## Handle a refused write

A `set` returns once the service has put the value, and raises
[`BoxPutError`][redsun.device.sharedbox.BoxPutError] when the service refuses
it, for example a value below the attribute's `min`. The error carries the
attribute's name and the service's message:

```{.python}
--8<-- "docs/examples/box_detector.py:refused"
```

A command that raises in the service raises `BoxPutError` in the session too.

## Name a stream of your own

A service can send data the controller doesn't hold, such as counts, on a
`sharedbox` [stream](../explanation/glossary.md#sharedbox) it makes itself. The device gets the same prefix as the
service, so it builds the stream's name with
[`stream_name`][redsun.device.sharedbox.stream_name]:

```{.python}
--8<-- "docs/examples/box_detector.py:stream"
```

Under the prefix `MYAPP:DET`, that names `MYAPP:DET:counts`. Agree on the last
part between the service and the device, which usually come from the same
package. `stream_name` refuses the part `fastcs`, since the transport's own
boxes use it.

## Reconnect after a restart

Each start of the service gives its boxes new names, and the index tells a
device what they are. A device connected to a service that has restarted
keeps the old boxes, so connect it again:

```python
await detector.connect(force_reconnect=True)
```

Signals you observe keep their subscribers across the reconnect.

## What the transport refuses

`BoxTransport` refuses some controllers when it starts, and the service then
exits with the reason:

- an attribute whose datatype is `Table`;
- an attribute or command whose name contains `__`, which the transport uses
  for its own fields;
- a controller with more attributes and commands than one box can hold, or a
  controller tree whose description is larger than the index can hold;
- more than one controller given to one `fastcs.control_system.FastCS`, the
  object that serves controllers over transports.

## The example in full

??? example "The service"

    ```{.python}
    --8<-- "docs/examples/box_service.py"
    ```

??? example "The session"

    ```{.python}
    --8<-- "docs/examples/box_detector.py"
    ```
