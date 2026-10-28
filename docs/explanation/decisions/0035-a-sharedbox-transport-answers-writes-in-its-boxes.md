# 35. A sharedbox transport answers writes in its boxes

Date: 2026-10-28

## Status

Accepted

## Context

A session reaches a `fastcs` service through a
[transport](../glossary.md#transport), and until now both transports were
network protocols: [Channel Access](../glossary.md#channel-access) and
[PVAccess](../glossary.md#pvaccess). A session and a service on the same
computer gain nothing from a network server between them, so a third
transport serves the controller through [`sharedbox`](../glossary.md#sharedbox)
instead, as [boxes](../glossary.md#box) in shared memory.

`sharedbox` gives a process typed fields to write and a way to wait for a
field to change, but no way to send a request and wait for its answer. A
write still has to behave as it does over PVAccess: `set()` returns once the
service has put the value, and raises with the service's message when the
service refuses it. So the transport had to decide how a write travels and
how its answer comes back.

It also had to decide how a controller's attributes are laid out in boxes.
`sharedbox` refuses to open a box unless the process opening it declares the
same fields as the process that made it. A controller whose attributes are
read from the hardware when it connects can't have its fields written down
ahead of time, so the session has to learn them from the service.

## Decision

- **A write travels in request fields of the controller's box, and the answer
  in fields the service writes.** For a writable attribute `exposure`, the
  session writes the value and a request number, and the service answers with
  the number it has served and an error, empty on success:

  ```python
  # the session
  box.update(exposure__setpoint=12.5, exposure__request=7)
  # the service, once the put has returned or raised
  box.update(exposure__error="", exposure__done=7)
  ```

  The session writes only the setpoint and request fields, and the service
  only the error and done fields, so the two processes never write the same
  field. The service writes the error and the done number in one update, so
  the session never reads a new number beside an old error. `set()` waits
  until `exposure__done` reaches its own request number, which keeps two
  writes, or a write after one that timed out, paired with their own answers.
  A refused write raises `BoxPutError` with the attribute's name and the
  service's message.

- **Each controller gets one box, and one index box describes them all.** The
  index has a fixed name under the service's prefix. It holds the controller
  tree as JSON: for each controller, its box name, its attributes with their
  datatypes, its commands and its sub-controllers. Both sides build a
  controller's box class from that description with one function, so the
  session's fields always match the service's:

  ```python
  index = ServiceIndex.attach("MYAPP:DET:fastcs:index")
  description = json.loads(index.description)
  root = box_class(description).attach(description["box"])
  ```

- **Each run of the service names its boxes anew.** A box is named
  `<prefix>:fastcs:<run>:root`, with a sub-controller's path after `root`,
  and `<run>` is six random hex digits picked when the service starts. On
  Windows a box lives until every process has closed it, so a restarted
  service could not make a box under the old name while a session still held
  it. The index keeps its name and lists the new ones, so a device reconnects
  by reading it again.

The options weighed for the write were a pair of streams and a request and
reply primitive in `sharedbox` itself. A pair of streams sends each request
as an item and each answer as another:

```python
requests.send({"attribute": "exposure", "value": 12.5, "id": 7})
answer = await replies.receive()  # the answer to 7, or to a write before it?
```

A request number in each item would pair the two, but the session would still
read every answer a timed-out write left on the stream before reaching its
own. A box holds only the latest answer, so the session compares one number
and reads one error. A primitive in `sharedbox` would have been the cleanest, but asking for
it meant a design and a release of another project before this transport
could ship.

The options weighed for the layout were one box per attribute and box classes
declared in the service's package. One box per attribute turns a controller
of 150 attributes into 150 boxes, each opened and watched on its own. Classes
declared ahead of time fail on the case that decided it: a controller whose
attributes come from the hardware has no class to declare until it connects.

## Consequences

- A device names no field.
  [`BoxDeviceConnector`][redsun.device.sharedbox.BoxDeviceConnector] fills its
  signals, commands and sub-devices from the index, as the connector
  `ophyd-async` ships for `fastcs` over PVAccess does from that service's list
  of records, and checks the ones the class declares.
- The transport lives behind the `sharedbox` extra, in
  `redsun.services.sharedbox` and `redsun.device.sharedbox`. A session that
  doesn't use it never imports `sharedbox` or `fastcs`.
- The service and the session have to run on the same computer.
- A `Table` attribute is refused, since a table has no row limit to size a
  field with.
- A service starting under a prefix removes the boxes a previous run left
  there, so a run that crashed leaves nothing behind on Linux.
