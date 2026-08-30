# 10. Toolkit hook points

Date: 2026-08-29

## Status

Accepted

Supersedes the build phase registry and the two container hook points of
[8. Container hooks and the build phase registry](0008-container-hooks-and-the-phase-registry.md).
The rest of that record stands: hook points are still named by the method they
call, still take one provider each, and are still generic protocols with a
per-toolkit alias.

## Context

Five hook points shipped. Two are used, and both by one provider, which supplies
the application object and puts a stylesheet on it. Nothing declares the other
three.

That is not merely low uptake. Reading back what the three were for shows two
different mistakes.

`configure_build` exists to serve the phase registry. The registry was
introduced because `build` was a straight-line body with no way to add a step to
it, and `configure_build` is the point at which a provider calls
`register_phase`. Its whole purpose is letting a hook rearrange the build.

`configure_session` has no recorded rationale at all. It was added because
"after everything is built" sounded like a moment somebody would want.

The registry itself has no caller outside this project's own tests.
`register_phase`, `unregister_phase`, `phases` and `sig_phase_complete` are
public API that nothing uses.

Underneath both is a question ADR 0008 did not settle: what a hook is allowed to
do. Left open, it grew to include changing what the container builds and in what
order, which put lifecycle callbacks and component assembly in the same
mechanism. The case that exposed it was a bundle wanting one object shared
between several view components. Routing that through a hook was reachable and
wrong: it is a dependency, and the container already resolves dependencies.

## Decision

**A hook never varies how a component is built.** It is a callback at a fixed
point in the toolkit's startup sequence, it runs only if declared, and it has no
say in what the container assembles or in what order. Anything that shares state
between components is a provider in the dependency graph.

**The build sequence is a straight-line body again.** `register_phase`,
`unregister_phase`, `phases` and `_phases` are removed, and with them
`configure_build`, which had nothing left to address. Four orderings are
load-bearing - the bus before everything, devices before presenters, every
component before wiring, every provider registration before any injection - and
a body states them where a registry only preserved them.

**`configure_session` is removed.** A component that wants to act on the session
it is part of asks for what it needs through the container's own injection,
which is checked, ordered, and visible to a reader of the class. A hook running
after the build is a second way to reach the same components with none of that.

**Every hook point belongs to a toolkit.** `AppContainer` declares none, and
naming one on it is refused. `QtAppContainer` declares four:
`create_application`, `configure_application`, `during_build` and
`configure_main_view`. A container for another toolkit declares the moments that
toolkit actually has, rather than inheriting moments defined for a different
one. This is what ADR 0008 already said about the *objects* a point receives,
applied to the set of points as well.

**`during_build` is a span, not a moment.** A splash screen appears before
anything is built, reports progress while it is, and closes once the window is
on screen, so it surrounds the sequence rather than sitting at a point in it.
The hook returns a context manager, entered before the first component is built
and left after the window is shown, yielding a callable that the container calls
with the name of each step.

Four properties follow, and are the reason for the shape:

- The close is guaranteed, a failed build included. A device that fails to
  construct, leaving a splash on screen over an application with no window, is
  the outcome a `show`/`close` pair gets wrong and a `with` block cannot.
- The container never learns what a splash is. There is no `show`, `update` or
  `close` vocabulary in `AppContainer`; it opens a block and calls a reporter.
- No signal is needed. `sig_phase_complete` is removed, and it was the only
  psygnal `Signal` on `AppContainer`, so `__weakref__` leaves its `__slots__`.
- Nothing branches on whether a hook was declared. With no provider the
  container enters a `nullcontext` over a reporter that discards what it is
  given, so the build has one path.

The point is named for its shape rather than its first use: a busy cursor, a
profiler or a logging context belongs at the same moment and is not a splash.

**The span opens on `run`, not on `build`.** `build` is what a test drives, and
a test wants no splash; `run` is the desktop entry point, and is where the
window is shown, which is where the span has to close.

**One provider per point.** Several hooks at one moment is not supported. There
is no case for it, and the constraint it would impose is worth stating: one
attribute name holds one provider, so a sequence would require a point to stop
being named by the attribute that declares it.

## Consequences

- `AppContainer` calls no hook point. A `hooks` section naming one is refused by
  name, listing what the container does call, which for the base container is
  nothing.
- A session that themed its application or supplied its own `QApplication` is
  unaffected: `create_application` and `configure_application` keep their names,
  their signatures and their behaviour.
- A session that registered a build phase has no replacement, by intention. The
  work belongs in a component, which the container builds, orders and injects.
- The build reports its steps as `virtual container`, `devices`, `presenters`,
  `views`, `providers`, `wiring` and `injection`. Those names are now part of the
  public surface, since a `during_build` provider displays them.
- A `during_build` provider needs no `shutdown`. Its context manager closes what
  it opened, and teardown for the other points is unchanged.
- The container-bound protocol aliases are gone. Every remaining protocol is
  parameterised on a toolkit object, so the type-level tests that pinned a
  provider to a container implementation no longer have a subject.
- A container for a new toolkit is written the way `QtAppContainer` is: declare
  the points in `_hook_keys`, and call each where the toolkit reaches it. That
  path is exercised by a container declaring two points of its own, so the
  machinery is tested without a toolkit present.
