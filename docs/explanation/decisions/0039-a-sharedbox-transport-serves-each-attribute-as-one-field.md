# 39. A sharedbox transport serves each attribute as one field

Date: 2026-11-17

## Status

Accepted. Supersedes
[35. A sharedbox transport answers writes in its boxes](0035-a-sharedbox-transport-answers-writes-in-its-boxes.md)
in how a controller's box is laid out and how a write travels. Its index box,
its box names and its choice of one box per controller still hold.

## Context

ADR 35 built a write out of plain fields, because `sharedbox` had no way to
send a request and wait for its answer. A writable attribute took five
fields of its controller's box: the value, the setpoint, a request number,
the number the service had served and the service's error. An array took
two more for the shapes of its value and its setpoint. The session and the service each ran their own code to number
requests, pair answers with them and pad arrays to a fixed size, and a
session could not tell a service that had died from one that was quiet.

`sharedbox` 0.10 adds what that code stood in for. An attribute field holds a
value, a setpoint and the time its writer published them. A field can be
served, so a process sends a request to the field's owner and awaits the
answer, with the owner's exception raised on the other side. An array field
holds any shape up to a maximum, and `segment_status` says whether the process
that created a box still runs.

## Decision

**Each attribute and command is one field of its controller's box, named as
the attribute, and writes travel as `sharedbox` requests.** A read-only
attribute is an `Attr`, a writable one a `Setting`, and a command an
`Attr[None]` the service serves as a call.

For a writable attribute `exposure`, ADR 35's session wrote a setpoint and a
request number, then waited for the service to echo the number:

```python
# before
box.update(exposure__setpoint=12.5, exposure__request=7)
# ... until box.exposure__done == 7, then read box.exposure__error
```

The field is now one `Setting`, which the service serves and the session
writes with a request:

```python
# after
class Detector(SharedBox, identity="redsun.services.sharedbox"):
    exposure: Setting[float] = attr()

await box.exposure.set(12.5)  # raises if the service's put raised
```

The service's handler publishes the setpoint, puts the value on the
attribute, and returns. The device turns a failed request into the
`BoxPutError` it raised before, with the service's own message, so code
using the device sees no change.

The two options weighed were keeping ADR 35's layout on the newer
`sharedbox` and moving to one field per attribute. Keeping the layout would
have cost nothing at once, but it kept the request numbers, the padding and
the extra fields per attribute, all of which the library now does for the
transport. The case that decided it was a service that dies: under ADR 35 a
write to it waited for an answer that never came, while a `sharedbox`
request fails as soon as its server is gone.

## Consequences

- A device raises
  [`ServiceExitedError`][redsun.device.sharedbox.ServiceExitedError], a
  `ConnectionError`, from a read, a write or a command once the service that
  created its box has stopped. An `observe_value` already running only stops
  receiving values, because a backend's callback has no way to deliver an
  error.
- A reading carries the time the service published the value, instead of the
  time the session read it.
- `sharedbox` lets the newest of several waiting requests win. Writes to one
  signal from one session are each served in order, because the signal holds
  a lock around its request. A write from another device or process that
  is replaced before the service reaches it raises `BoxPutError` with "superseded by
  another writer".
- An array keeps the shape it was written with, up to the maximum its
  datatype declares, and an unsigned integer is stored as `numpy.uint64`.
- An attribute named like a method of `SharedBox`, such as `name` or `close`,
  takes the field `name_` in the box. The device reaches it through the same
  function, so its signal keeps the attribute's name.
- Names containing `__` are allowed, since the transport no longer uses
  them.
- The box identity is the same string, but its fields differ, so a session
  and a service of different `redsun` releases refuse each other's boxes
  with `sharedbox.SchemaMismatchError`.
- The 256-field limit of a box now counts attributes and commands, not five
  or seven fields per writable attribute.
- Two names that would take the same field, such as `name` and `name_`, are
  refused when the service starts.
