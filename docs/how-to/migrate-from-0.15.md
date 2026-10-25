---
icon: lucide/arrow-right-left
---

# How to migrate from 0.15

Release 0.16 removes the two things 0.15 deprecated, changes what a view of
plan progress receives, moves some axes to another box of the positioner,
removes two helpers the positioner no longer uses, and changes what a session
does when a service does not start. This page gives each change with what to
write instead. The [changelog](../reference/changelog.md) lists everything
else the release changed.

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

## Positioner boxes follow the device holding the axes

The positioner groups axes by the device that holds them directly. A device
whose axes are its own children, such as a stage with the attributes `x` and
`y`, keeps its box and its saved positions. A device whose axes sit one level
deeper sees them move. This stage holds its axes in `motors`:

```python
class MyStage(StandardReadable):
    def __init__(self, name: str = "") -> None:
        self.motors = DeviceMap({"x": MyAxis(), "y": MyAxis()})
        super().__init__(name=name)
```

In 0.15 its axes were rows of the box `stage`. Now they are rows of the box
`stage-motors`, titled `stage / motors`, so positions saved under `stage` no
longer match a box: the view leaves them out and logs a warning naming
`stage`. Move the stage to each position again and save it. To keep the box
`stage` instead, hold the axes as attributes of the stage, as in
`self.x = MyAxis()`. An `include` list naming `stage` changes the same way, to
`stage-motors`.

## `find_axes` and `walk_axes` are gone

`redsun.utils.devices.find_axes` and `walk_axes` gathered every axis below one
device. To find the axes below a device, walk it with `walk_devices` from
`ophyd-async` and keep what is an [`Axis`][redsun.utils.devices.Axis] and not a
signal:

```python
# 0.15
axes = find_axes(stage)

# now
axes = {
    path: device
    for path, device in walk_devices(stage).items()
    if isinstance(device, Axis) and not isinstance(device, Signal)
}
```

## Progress views receive the scopes

`RunEngine.sig_progress` carries the open progress scopes themselves, as
[`PlanProgress`][redsun.engine.PlanProgress] objects, so `ProgressState` is
gone. A scope gives its `name`, its `parent` scope, and in `update` the last
`WatcherUpdate` of `ophyd-async` it reported, or `None` before the first. The
update holds what the plan or the device reported and nothing more, so a view
that showed `fraction` computes it from `current`, `initial` and `target` when
the update has none. The scopes are the engine's own, and the engine replaces
their `update` after the emission, so a view reads it once for each emission.

A view that passes the scopes on to the plan widget only changes its
annotation to `tuple[PlanProgress, ...]`. A view that reads the values reads
them from the scope's update:

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
`ophyd-async`, whose parameters can be passed by position or by name. A type
checker therefore refuses a function that takes only `**kwargs`, or whose
parameters are keyword-only; declare the parameters as plain named ones. A
fraction reported alone reaches the watcher alone, with `current`, `initial`
and `target` left `None`, and a device's status that reports no unit gives
`unit` as `None` instead of `"unit"`.

## A strict session stops when a service does not start

A [strict session](../explanation/glossary.md#strict-session) now stops when
any service fails to start, even one that no device names. In 0.15 such a
session ran on, and stopped only if a device on the service could not be
built. If the session declares a service it no longer uses, remove the
service from the session file. If a service may be missing while you work,
leave `strict` off for those runs:

```python
MyApp({"strict": False}).run()
```

## A prefix that defaults to `None` is optional

A device declared with `service="x"` whose `prefix` argument defaults to `None`
is now built when the service does not start. The session leaves `prefix` out,
so the device gets `None`, and the build summary lists it under
`Built without`. In 0.15 the session skipped the device. To keep it skipped,
give `prefix` no default:

```python
# 0.15: skipped when the service does not start
class MyCamera(StandardReadable):
    def __init__(self, prefix: str | None = None, name: str = "") -> None: ...


# now, to keep it skipped
class MyCamera(StandardReadable):
    def __init__(self, prefix: str, name: str = "") -> None: ...
```
