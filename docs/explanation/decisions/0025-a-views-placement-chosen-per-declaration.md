# 25. A view's placement chosen per declaration

Date: 2026-10-07

## Status

Accepted

## Context

The session needs to know where a view goes before it builds the view. It
uses this to refuse a place the frontend cannot show, and to show an error
message where a failed view would have been. The session could read the place
only from the view's class. To place one view class in different places, a
view returned its placement from a property, which the session could read
only after building the view. To move a built-in view, you had to subclass
it.

## Decision

- `placement` is a reserved key of a view's declaration. The session keeps it
  and never passes it to the constructor. A view whose constructor takes a
  `placement` of its own is refused.
- The declaration holds the placement: the declared one, or else the class
  attribute. The check at declaration, the error placeholder and the code
  that attaches views all read it from there.
- A session file gives a word or a one-key mapping. The frontend reads it
  with `read_placement`, so the core names no toolkit word.
- Docks on the same edge with the same group open as tabs.
- Returning `placement` from a property is deprecated, and removed in 0.16.

Two other options were rejected. An `area` keyword on the built-in views
would move only those views, and a failed one's placeholder would still use
its class's edge. A `place` class method on each view would need code in
every view to make it movable, and would put a toolkit word in the core.

### Before

```python
from typing import Annotated

from qtpy.QtWidgets import QWidget

from redsun import AsView, Declare, Placement
from redsun.qt import Area, Dock, QtSession
from redsun.view.qt.builtins import PositionerView


class MyView(QWidget):
    def __init__(self, name: str, parent: QWidget, area: Area = "left") -> None:
        super().__init__(parent)
        self.name = name
        self.area = area

    @property
    def placement(self) -> Placement:
        return Dock(self.area)


class LeftPositioner(PositionerView):
    placement: Placement = Dock("left")


class MyApp(QtSession):
    # checked only once built; if MyView raises, no placeholder at all
    right_panel: Annotated[AsView[MyView], Declare(area="right")]
    # a built-in view moves only through a subclass
    stage: AsView[LeftPositioner]
```

### After

```python
from typing import Annotated

from qtpy.QtWidgets import QWidget

from redsun import AsView, Declare, Placement
from redsun.qt import Dock, QtSession
from redsun.view.qt.builtins import PositionerView


class MyView(QWidget):
    placement: Placement = Dock("left")

    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.name = name


class MyApp(QtSession):
    # checked when declared; if MyView raises, its placeholder docks right
    right_panel: Annotated[AsView[MyView], Declare(placement=Dock("right"))]
    stage: Annotated[AsView[PositionerView], Declare(placement=Dock("left"))]
```

## Consequences

- You can move any view, built-in or from a plugin, without writing code,
  from Python or from the session file.
- `AttachableComponent.placement` stays. It is the class's default, and the
  session reads the declaration's placement instead of the instance's.
- A plugin that returns its placement from a property gets a warning until
  0.16. After that it must declare the placement.
- The window layout design builds on the declared placement and the dock
  groups.
