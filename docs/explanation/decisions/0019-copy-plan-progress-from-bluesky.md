# 19. Copy plan progress from bluesky

Date: 2026-10-01

## Status

Accepted. Temporary: superseded once `bluesky` releases plan progress.

## Context

A plan widget should show how far a running plan has got. `bluesky` has no
released way for a plan to say so. Pull request
[bluesky#2078](https://github.com/bluesky/bluesky/pull/2078), resolving
[bluesky#2047](https://github.com/bluesky/bluesky/issues/2047), adds one: two
messages, `declare_progress` and `update_progress`, their plan stubs, a
`PlanProgress` status and a `RunEngine.progress_hook`. It is a draft.

## Decision

`redsun` copies that interface from the pull request at commit `c2040e7`,
with the same names, signatures and messages, so that a plan written against
`redsun.engine.plan_stubs` runs unchanged once `bluesky` ships its own.

One difference: `redsun` does not replay the two messages when a paused plan
resumes, which the pull request does. A replayed `declare_progress` would
find its scope still open and be refused. This follows a review comment on
the pull request.

On top of the copy, `redsun` adds `ProgressState`, a snapshot of one scope,
and `RunEngine.sig_progress`, which carries the open scopes to views, a
"Progress" group on each plan page, and `monitor_progress`, which follows a
device status with a scope. The engine finishes every scope a plan
left open when it goes back to idle, which the pull request does in parts of
the `RunEngine` a subclass cannot reach.

## Consequences

When `bluesky` releases plan progress:

- delete `redsun`'s `PlanProgress`, the two commands and the two stubs, and
  re-export `bluesky`'s stubs and `PlanProgress` under the same names;
- keep `ProgressState`, `sig_progress`, the engine's own `progress_hook` and
  the widget, which then follow `bluesky`'s objects;
- keep the two messages out of the replay if `bluesky` has not done so;
- rebuild `monitor_progress`, which is `redsun`'s own, on `bluesky`'s scopes.
