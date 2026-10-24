# 19. Copy plan progress from bluesky

Date: 2026-10-01

## Status

Accepted. Temporary: superseded once `bluesky` releases plan progress.
Amended on 24 October 2026: `PlanProgress` keeps its updates as `ophyd-async`
does, and `ProgressState` is gone.

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

`PlanProgress` also differs from the copy in how it holds an update. It is
generic over the type of the values it reports, keeps its last update as the
`WatcherUpdate` of `ophyd-async`, and passes it to watchers typed as the
`Watcher` of `ophyd-async`, so a scope and a device's status report in the
same shape. A fraction reported alone reaches the watchers alone, where the
pull request fills `current`, `initial` and `target` from it for the progress
bar of the terminal. A view reads the scope's update where it read a snapshot
the engine built before:

```python
# before
def on_progress(self, scopes: tuple[ProgressState, ...]) -> None:
    for scope in scopes:
        print(scope.name, scope.current, scope.fraction)


# after
def on_progress(self, scopes: tuple[PlanProgress, ...]) -> None:
    for scope in scopes:
        if scope.update is not None:
            print(scope.name, scope.update.current, scope.update.target)
```

The snapshot computed the fraction and dropped values that were not finite
numbers. Only the plan widget needs either, so the widget does both now, and
the engine passes on what the plan or the device reported: `update.fraction`
is a fraction the plan or device reported, never one computed from `current`,
`initial` and `target`.

On top of the copy, `redsun` adds `RunEngine.sig_progress`, which carries the
open scopes to views, a "Progress" group on each plan page, which computes
the fraction of its bar from a scope's update, and `monitor_progress`, which
follows a device status with a scope. The engine finishes every scope a plan
left open when it goes back to idle, which the pull request does in parts of
the `RunEngine` a subclass cannot reach.

## Consequences

When `bluesky` releases plan progress:

- delete `redsun`'s `PlanProgress`, the two commands and the two stubs, and
  re-export `bluesky`'s stubs and `PlanProgress` under the same names, unless
  `bluesky`'s scope does not hold its update as a `WatcherUpdate`, which code
  annotated with `PlanProgress[T]` or reading `update` relies on;
- keep `sig_progress`, the engine's own `progress_hook` and the widget, which
  then follow `bluesky`'s objects;
- keep the two messages out of the replay if `bluesky` has not done so;
- rebuild `monitor_progress`, which is `redsun`'s own, on `bluesky`'s scopes.
