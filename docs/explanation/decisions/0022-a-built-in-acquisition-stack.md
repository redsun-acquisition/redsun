# 22. A built-in acquisition stack

Date: 2026-10-05

## Status

Accepted

## Context

`redsun` gave plugins the parts to run plans from a window (plan
specifications, plan widgets, actions, progress, a run engine) but no
presenter or view putting them together, so a plugin wrote both. One such
pair reported a plan that raised as if it had succeeded, showed a plan as
running before the presenter had accepted it, sent actions to the last plan
launched even after it ended, and needed one link per action manager, which a
session written from its own example left out. Other components reached its
engine and its deferred settings through an attribute or a protocol of that
plugin.

## Decision

- `redsun` ships `AcquisitionPresenter` and `AcquisitionView`, under the
  plugin id `acquisition`. They run any plan a component offers; they offer
  none of their own.
- The presenter owns the `RunEngine` and its `Deferrals`, and shares both
  through `provides`, so any component asks for them in `setup` by type.
- A plan that raises is logged with its traceback and reported on
  `sig_plan_failed`; the view shows the message on the plan's page until it
  runs again. A stopped plan is reported as done; a plan aborted when the
  session shuts down is reported neither way, and the shutdown waits for its
  cleanup.
- The view shows a plan running only on `sig_plan_started`, which the
  presenter emits once the engine has started the plan. A pause or a stop
  asked for before then is applied as soon as the plan starts.
- The presenter relays the actions of every component holding an
  `ActionManager` (`HasActions`) through one signal.
- The presenter names each run's files through the session's path provider,
  and relays its base directory to and from the view.
- Protocols stay free of `redsun` types where their behaviour allows, so a
  plugin may copy one rather than import it; `HasActions` names
  `ActionManager`, since a plan waits on it.

## Consequences

- A session holds one acquisition presenter: two would both share a
  `RunEngine`, and the session refuses two components sharing one type.
- A session writes twelve links for this stack. Shortening the wiring of the
  built-in stacks is left to a later decision.
- A plugin's own plan presenter and view can be replaced by these, its plans
  and its actions moving to a component that offers them.
