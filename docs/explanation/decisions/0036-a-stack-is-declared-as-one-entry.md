# 36. A stack is declared as one entry

Date: 2026-10-30

## Status

Accepted

## Context

A stack is a presenter and its views written to work together, and a
session declared each half on its own and joined them with a pairing. The
built-in acquisition stack took three entries in a session file:

```yaml
presenters:
  acquisition:
    plugin_name: redsun
    plugin_id: acquisition
views:
  acquisition_view:
    plugin_name: redsun
    plugin_id: acquisition
pairs:
  - [acquisition_view, acquisition]
```

Nothing told the session that the two belonged together, so a session could
declare one half and learn of the missing one only when the view reported it
was not set up. A plugin whose presenter has two views needed three entries
and two pairs. ADR 22 left shortening the wiring of the built-in stacks to a
later decision, and ADR 23 shortened it to one pairing; this decision removes
the pairing from what a session writes.

Three readings of "a stack as one thing" were weighed:

- A shorthand: the session turns one entry into the declarations and the
  pairing it would otherwise be given, and builds, names and wires the halves
  as before.
- A namespace: the halves are addressed as `stack.component` in `wiring`,
  `shortcuts` and `Settings`, which changes the syntax of the session file
  and every saved setting.
- An encapsulation boundary: the stack hides its halves and is reached only
  through ports of its own, which needs ports for a group of components
  before it can start.

The shorthand gives a session everything it asked for, one entry that always
brings both halves and their links, without changing how a half is named or
reached.

## Decision

- A stack is a plain class whose annotations name one presenter and one or
  more views, each under a role. It has no base class. A stack holding
  anything else, such as a device, or holding no presenter, two presenters or
  no view, is refused when the session reads it.

  ```python
  class AcquisitionStack:
      presenter: AsPresenter[AcquisitionPresenter]
      view: AsView[AcquisitionView]
  ```

- A plugin lists its stacks in the `stacks` section of its manifest. A session
  class declares one with `AsStack`, and a session file under `stacks`:

  ```python
  class MyApp(QtSession):
      acquisition: AsStack[AcquisitionStack]
  ```

  ```yaml
  stacks:
    acquisition:
      plugin_name: redsun
      plugin_id: acquisition
  ```

- The presenter takes the stack's name and each view `<stack>_<role>`, so the
  entry above makes `acquisition` and `acquisition_view`, the names a session
  wrote before. A half name that is already declared is refused.
- The session turns a stack into ordinary declarations before the first build
  step, so each half is checked, built, skipped on failure and set up as any
  component is. The wiring step pairs the presenter with each view after the
  file's `pairs`, so a pair listed there as well is linked once.
- A half's keywords come from the stack class's `Declare`, then the role's
  entry in the session file, then the session class's `Declare`, each
  replacing the one before.
- The name "stack" is the one the docs already gave this pair. "Unit" was
  set aside because `redsun` already reports physical units, such as the
  `units` of a signal.

## Consequences

- The built-in stacks ship as `AcquisitionStack`, `PositionerStack` and
  `LightStack`, under the ids `acquisition`, `positioner` and `lights`. The
  presenter and view ids stay, so a session file that declares the halves one
  by one works as before.
- A session class holds the stack under the attribute it declared, as an
  instance of the stack class whose roles are the built halves, such as
  `self.acquisition.view`. A half is not held under its own name.
- A namespace or a boundary for a stack's halves can still be added later on
  top of the stack class, which already lists the halves by role.
