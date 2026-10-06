# 23. Pairing two components

Date: 2026-10-06

## Status

Accepted

## Context

A session connected two components one link at a time, in `wire` or in the
`wiring` section of its file. The built-in acquisition stack needs twelve
links between its presenter and its view, the positioner nine and the light
stack seven, and a session written from an example could leave one out.
ADR 22 left shortening this to a later decision.

## Decision

- The session names the pair. A file lists it under `pairs`, a `wire`
  method yields `links_between(a, b)`. Two components are never connected
  because both are declared: that would make connections the session never
  states, and is ambiguous as soon as two views of one kind exist.
- A slot says which signals reach it, with `slot(signal=...)`, one
  attribute name or a tuple of them. Pairing A with B connects each signal
  of A to each slot of B naming it, and each signal of B to each slot of A.
  A method per component returning its links was rejected, since nothing
  could list what a pairing connects without running it; so was a separate
  list of links per pair, a third thing to keep in step with two classes.
- `pairs` is a list of two names. A pairing goes both ways, which a list
  says and a mapping does not. A bare component name inside `wiring` was
  rejected, since a reader could not tell a pairing from a link without
  counting dots; so was a key on a component's declaration, which would
  make a link between two components belong to one of them.
- A pairing whose two components built and that connects nothing raises
  `WiringError` naming both, as a misspelt path in `wiring` does.
- A link is made once. A link already made by `wire`, by `wiring` or by
  another pairing is skipped with a debug record, so a pairing can be added
  to a session that still lists the same links. A link listed twice used to
  be connected twice.
- The links of a session are made, recorded and undone by an internal
  object of their own, which pairing builds on; `links_between` is a public
  function that needs no session, so `wire` and the file match the same way.
- A pairing checks the number of arguments, as every link does, and not
  their types. `psygnal`'s own type check refuses correct links of the
  built-in stacks, such as `Signal(frozenset)` into a slot taking
  `frozenset[str]`, and cannot read an annotation imported only for type
  checking.
- The positioner view's stop signal is `sig_stop_device`, not `sig_stop`:
  the acquisition view's `sig_stop` stops the plan, and a pairing matches
  names. `psygnal` accepts a slot taking fewer arguments than its signal
  sends, so with one name for both, pairing the acquisition presenter with
  the positioner view to pass on the locks would also have connected
  stopping a device to stopping the plan.

## Consequences

- Each built-in stack is connected with one pairing. The views' `set_locked`
  names `sig_locks_changed`, so pairing the acquisition presenter with the
  light view or the positioner view also passes on the engine's locks.
- A pairing connects every name two components share, so a name says what
  its signal does. Pairing the acquisition presenter with the positioner
  view passes on the locks and nothing else.
- Device signals are not matched, and a pairing names exactly two
  components; both stay explicit links.
