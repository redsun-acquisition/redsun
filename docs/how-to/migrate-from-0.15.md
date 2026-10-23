---
icon: lucide/arrow-right-left
---

# How to migrate from 0.15

Release 0.16 removes the two things 0.15 deprecated. A project that ran on
0.15 without a `DeprecationWarning` from `redsun` runs on 0.16 unchanged, and
this page gives each removal with what to write instead. The
[changelog](../reference/changelog.md) lists everything else the release
changed.

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
