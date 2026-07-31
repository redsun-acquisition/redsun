# 6. Application-declared wiring

Date: 2026-07-31

## Status

Accepted

Extends [4. Owner-scoped signal lookup](0004-owner-scoped-signal-lookup.md).

## Context

Signal connections were made by consumers, which reached into the container's
signal registry for names they hoped existed:

```python
sigs = find_signals(container, ["sig_pre_launch_notify", "sig_plan_done"])
if "sig_pre_launch_notify" in sigs:
    sigs["sig_pre_launch_notify"].connect(self._on_pre_launch)
```

Four problems follow from that shape, and ADR 0004's owner scoping addressed
only the first.

**A rename breaks the connection silently.** The emitter and the consumer agree
on a string, checked by nobody. ADR 0004 records this happening across the
redsun and redsun-mimir boundary during the `sigCamelCase` rename.

**Optionality is expressed by silence.** The `if name in sigs` guard makes a
typo, a rename, an uninstalled plugin, and a deliberately absent optional
collaborator indistinguishable at runtime.

**No one owns the graph.** Each component decides for itself what it listens to,
so no single place says how an application is wired. The answer is distributed
across every `inject_dependencies` in every installed plugin.

**Nothing is recorded.** A pull-based connection leaves no trace, so the graph
cannot be reported, and `shutdown` cannot release what was connected.

psygnal supplies the machinery underneath (class-scoped declaration, signature
validation at connect, grouping, cross-thread delivery) but has no cross-object
concept: nothing in it says which component's signal reaches which component's
method. That is the gap.

An earlier design filled it with nominal *contracts*: a component published a
signal under a name and consumed one with a decorator, and the container matched
the two. It was implemented and dropped. It kept the knowledge of the graph
inside the components, needed a process-global registry with qualified names,
short names and per-session bindings to keep two packages from colliding, and
left the graph emergent, so a report was necessary rather than useful.

## Decision

A component states what it offers; the application states what is connected.

**A method opts in.** `slot` marks a method as connectable, which makes its name
and signature part of the component's public surface. An unmarked method cannot
be connected. Signals need no marker: a public `Signal` attribute, or a member
of a `SignalGroup`, is already a port, addressed by the member name in the group
case.

**The application connects.** `AppContainer.wire` is a hook that runs after
every component is built and before dependency injection. Inside it, a
component attribute resolves to its built instance, so a connection reads as
`self.connect(self.det_ctrl.sig_new_data, self.img_widget.update_layers)`. A
session built from a configuration file uses the `wiring` section, addressing
each end as `component.port`. Both forms end in the same
`VirtualContainer.connect`.

**Validation is psygnal's, at connection time.** The argument count is always
checked; argument types are checked as well when the signal names them. redsun
adds only the port names to the failure, so the error identifies both ends.

**Thread affinity belongs to the component**, declared once on the class
(`__redsun_slot_thread__`), overridable per slot and per connection. `QtView`
declares `"main"`, which removes by construction the class of defect where one
Qt slot is connected without marshalling and its neighbour is not.

**Every link is recorded.** `VirtualContainer.connections` is the graph, and
`disconnect_all` releases it during `shutdown`.

`find_signals` and `register_signals` are unchanged and still work. They are
demoted to an escape hatch for dynamic lookup, not the way components are wired.

## Consequences

- The wiring of an application is readable in one place, in the container class
  or in its configuration file. Adding a producer to an existing consumer is one
  line there, and it is the same line whether the producer ships with redsun or
  with a third-party plugin.
- A connection that cannot be made fails the build with both port paths in the
  message, rather than not happening.
- A component gains no knowledge of the application it is in. A viewer that
  accepts frames names no producer, and a plugin author cannot express a
  connection to a component they do not ship. That is deliberate: the
  composition root is where that knowledge belongs.
- The cost is that a plugin no longer arrives pre-wired. A deployment that
  installs a new frame producer must add a line for it. This is the trade
  against the contract design, which auto-connected at the price of a global
  name registry and an emergent graph.
- Marking a method makes it API. Components migrating from `inject_dependencies`
  will find their slots are private methods and should rename them, since a
  wiring declaration naming `_update_layers` is a contradiction.
- Payload types become worth declaring. `Signal(object)` passes any slot;
  `Signal(FrameBatch)` makes the connection a real type check at build. Existing
  signals are unaffected, but a new signal should name its payload.
