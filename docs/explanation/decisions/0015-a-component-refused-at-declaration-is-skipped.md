# 15. A component refused at declaration is skipped

Date: 2026-09-19

## Status

Accepted, and applied to `redsun.experimental` only. Amends
[11. Tolerating a component that fails to build](0011-tolerating-a-component-that-fails-to-build.md),
which kept the check of a presenter's or view's constructor at declaration
fatal. `redsun.containers` keeps that rule.

## Context

A session builds what it can. A device that does not connect, or a presenter
whose constructor raises, is logged and skipped, and the session runs without
it. A class that fails a check when its declaration is read was the exception:
a presenter taking `name` only positionally, a view declaring no placement, or
an `async def setup` raised a `TypeError` from `Session.build` before anything
started, and the session did not run at all.

The checks have grown: a view under Qt must start its constructor with
`(name: str, parent: QWidget)`, so a view written before that rule, possibly
one a plugin supplies, would stop a session whose other components are fine.
The mistake belongs to one component, and ending the session over it is the
outcome the rest of the build avoids.

## Decision

**A component that fails a declaration check is logged and skipped, like one
that fails to build.** `refusal` in the declarations module returns the
`TypeError` that `check` raises, and `Declaration.refusal` keeps it. The
session records it with the build failures, never builds that component, and
names it in the build summary. A wiring rule naming it is warned about and
skipped, and a component whose `setup` needed it is reported as not set up, as
for any component that failed.

**The protocol and placement of a built instance are checked as it is built.**
A placement answered by a property is only known on the instance. It was
checked when the session was sealed, after every component was built and set
up, and a failure ended the session. It is now checked the moment the
constructor returns, before the instance is registered, and a failure skips
that component. A Qt view built with the window as its parent is removed from
the window.

This covers the checks made on one class. The checks relating two components
when the store is filled, a constructor asking for what another component owns
and a `setup` reaching into a later layer, still raise.

**What is wrong with the session itself stays fatal.** A declaration naming
something that is not a class, a component name hiding an attribute of the
session, a malformed `storage`, `services`, `hooks` or `wiring` section, and a
wiring rule naming a component never declared or a port that does not exist
still raise. None of them is a component that could be left out.

## Consequences

- A session starts with a component whose class breaks a rule, and the log
  says which one and why:

  ```text
  Failed to build view 'plot': MyApp.plot is declared as a view, but Plot
  declares no 'placement'. A view says where it attaches; a component that
  attaches nowhere is a presenter.
  Not built: plot (view)
  ```

- A mistake in a component's class no longer stops the session. It is logged
  at `ERROR` and named in the closing summary at `WARNING`.
- A view whose placement property reads state its `setup` assigns cannot
  answer when it is checked, and is skipped. A placement has to be known when
  the constructor returns.
- `check` still raises, for a caller checking one class on its own.
