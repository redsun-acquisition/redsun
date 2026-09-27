# 18. Wire yields links

Date: 2026-09-27

## Status

Accepted. Amends
[6. Application-declared wiring](0006-application-declared-wiring.md), whose
`wire` connected components itself through `self.connect` and
`self.subscribe`, and whose file form was a list of `from:`/`to:` rules.
Everything else ADR 6 decided, a method opting in with `slot`, validation done
by `psygnal`, every link recorded, stays as written there.

## Context

`wire` called `self.connect` for a `psygnal` signal and `self.subscribe` for
an `ophyd-async` device signal, two methods for what is one relationship: a
signal reaching a slot. Whoever wrote `wire` had to remember which of the two
a given signal needed, and a helper shared between sessions had to take the
session as an argument to call either.

The file's `wiring` section was a list of `from:`/`to:` mappings. A list
merges by replacement across layered configuration sources: a later file
adding one link had to repeat every link an earlier file already declared, or
lose them.

Thread delivery could also be set on the individual `connect` or `subscribe`
call, ahead of the slot's own declaration. Two links reaching the same slot
from different places could disagree on its thread, though the slot is one
method and delivery is a property of it, not of the call that connects it.

## Decision

`Session.wire` returns an iterable of links instead of connecting anything
itself. A link is a tuple of a signal and the slot it reaches; the class
overrides `wire` as a generator:

```python
def wire(self) -> Iterator[Link]:
    yield self.motor_ctrl.sig_moved, self.motor_widget.update
    yield self.stage.readback, self.motor_widget.on_reading
```

The session tells a `psygnal` signal from a device signal apart by its type
when it makes the link, so one form covers both. A helper shared between
sessions is a plain generator that needs no session argument, used with
`yield from`.

`connect`, `subscribe` and `connect_paths` are no longer public; the session
makes each link itself as it iterates what `wire` yields. A `wire` that
returns `None`, an ordinary method with no `yield`, raises `WiringError`,
naming the mistake instead of silently wiring nothing. A link whose first
item is not a signal raises `WiringError` as well.

The `wiring` section of a session file changed from a list to a mapping from
a signal path to one slot path or a list of them:

```yaml
wiring:
  motor_ctrl.sig_moved: motor_widget.refresh
  acq_ctrl.sig_plan_done: [acq_widget.on_plan_done, path_provider.reset_plan]
```

A mapping merges by key across layered files: a later file adds a signal
without repeating the earlier ones, and naming a signal again replaces its
slots.

A link no longer takes a thread override of its own. The thread a slot is
delivered on comes from the slot's own declaration, then its class's, then
the session's default for the consumer, so a slot is delivered on the same
thread wherever it is reached from.

## Consequences

- `wire` states which signal reaches which slot and connects nothing, so
  the session is the only place a link is made.
- A `psygnal` signal and a device signal are written the same way in `wire`.
  The file names `psygnal` signals only, as before.
- A session file written with `from:` and `to:` is refused when it is read,
  and has to be rewritten as a mapping.
- A session file's `wiring` section reads as one line per link, and a later
  layer states only what it adds or changes.
- A slot has one thread, wherever it is connected from. A caller that wanted a
  one-off delivery thread for a single link no longer can; it declares the
  thread on the slot instead.
