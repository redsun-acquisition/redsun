---
icon: lucide/arrow-right-left
---

# How to migrate from 0.15

Release 0.16 removes the two things 0.15 deprecated, and changes what a view
of plan progress receives. This page gives each change with what to write
instead. The [changelog](../reference/changelog.md) lists everything else the
release changed.

## A view's placement can't come from a property

The session reads a view's placement before it builds the view, so the
placement has to be a plain class attribute or part of the declaration. A view
class that answers `placement` from a property, and whose declaration gives
none, is refused when the session reads its declarations: the view is left out
and the log says it has no placement. Set `placement` as a class attribute when
the place is always the same:

```python
# 0.15
class MyView(QWidget):
    @property
    def placement(self) -> Placement:
        return Dock("left")


# now
class MyView(QWidget):
    placement: Placement = Dock("left")
```

When the place depends on the session, give it in the declaration instead, as
[How to place a view](place-a-view.md) shows.

## `BUILD_STEPS` is gone

`redsun.session.BUILD_STEPS`, the tuple of the steps a session's build goes
through, is removed. Use the enumeration
[`BuildStep`][redsun.session.BuildStep]: iterate it for the steps in order,
and take `len(BuildStep)` for their count.

```python
# 0.15
from redsun.session import BUILD_STEPS

# now
from redsun.session import BuildStep
```

## Progress views receive the scopes

`RunEngine.sig_progress` carries the open progress scopes themselves, as
[`PlanProgress`][redsun.engine.PlanProgress] objects, so `ProgressState` is
gone. A scope gives its `name`, its `parent` scope, and in `update` the last
`WatcherUpdate` of `ophyd-async` it reported, or `None` before the first. The
update holds what the plan or the device reported and nothing more, so a view
that showed `fraction` computes it from `current`, `initial` and `target` when
the update has none. A view that passes the scopes on to the plan widget only
changes its annotation:

```python
# 0.15
@slot
def on_progress(self, scopes: tuple[ProgressState, ...]) -> None:
    for scope in scopes:
        print(scope.name, scope.parent, scope.current)


# now
@slot
def on_progress(self, scopes: tuple[PlanProgress, ...]) -> None:
    for scope in scopes:
        parent = scope.parent.name if scope.parent is not None else None
        current = scope.update.current if scope.update is not None else None
        print(scope.name, parent, current)
```

A watcher passed to `PlanProgress.watch` is now typed as the `Watcher` of
`ophyd-async`, whose parameters have names, so a type checker refuses a
function that takes only `**kwargs`. A fraction reported alone reaches the
watcher alone, with `current`, `initial` and `target` left `None`.
