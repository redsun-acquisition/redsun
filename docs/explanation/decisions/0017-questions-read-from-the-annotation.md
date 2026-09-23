# 17. Questions read from the annotation

Date: 2026-09-19

## Status

Accepted, and applied to `redsun.experimental` only. Builds on
[15. Collaborators arrive in `setup`](0015-collaborators-arrive-in-setup.md).

## Context

A component can ask the session which components can do something, rather
than for a value by its type. The experimental session spelled those questions
with three markers, `Requires[P]`, `RequiresOne[P]` and `RequiresMaybe[P]`:
`Annotated` aliases stating that a parameter was a question about `P` and how
many answers it took.

The markers carried machinery with them. The store keys on types, and it could
not tell a question from a value of the same shape, so the session generated a
key per question. A single answer was chosen before the build, from the
declared classes, which meant the protocol had to declare a method and the
choice had to be checked again once the instance existed. A value one
component shared could never answer a question, only another component could.

The annotation already says what the markers said. A parameter typed by a
protocol cannot be a value the store holds, as long as the store holds only
concrete objects, and the shape of the annotation gives the count.

## Decision

**A `setup` parameter annotated with a protocol is a question, and its shape
is how many answers it takes.** `P` takes the one object satisfying `P`,
`P | None = None` at most one, and `Mapping[str, P]` every component
satisfying `P`, by name. Every other annotation names a value, which the store
fills by type as before.

**The store holds concrete objects only.** A component, a value shared with
`provides`, and what the session itself provides are registered under their
classes. A component with a `provides` method annotated with a protocol is
skipped at declaration.

**The session answers a question itself, when `setup` runs.** Every component
exists by then, so it matches built instances, comparing members and call
signatures, and hands the answers to `setup` directly; `in-n-out` fills the
other parameters. A single answer may be a component or a value a component
shares, never the asking component itself, and never one from a later layer.
Where one answer is asked for, none or several raise, and if only a component
that failed to build could have answered, the asker is left not set up. A
census covers the components, the asking one included, across layers.

**A constructor asks only for devices.** Devices exist before any presenter or
view, so `DevicesOf[P]` stays, the one marker left, and the session fills it
when it builds the component. A protocol question in a constructor, a device
protocol or `DevicesOf` in `setup`, and a union of protocols skip the component
at declaration.

## Consequences

- A shared object answers both its own type and every protocol it satisfies:
  `viewer: ViewerModel` and `layers: HasLayers` receive the same object, and
  the component sharing it names neither consumer.
- A protocol asked about need not be `runtime_checkable`, may declare data
  members, and may be generic: `Reading[float]` is matched as `Reading`.
- Asking for exactly one answer and getting none or several fails when `setup`
  runs, after the devices have connected, rather than before anything is built.
- A command registered on the application is resolved by the store, which
  holds no protocol, so a command cannot ask a protocol question.
- `in-n-out` remains the store: the application's commands and the components
  are filled from the same one.
- Matching on shape still lets a component answer a question by accident, as
  the markers did.
