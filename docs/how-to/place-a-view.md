---
icon: lucide/layout-dashboard
---

# How to place a view in the window

Choose where a view of a Qt session appears: in a dock, in the centre, in a
menu or in a toolbar. [How a frontend shows a session on screen](../explanation/frontends.md)
explains what a [placement](../explanation/glossary.md#placement) is and how
a frontend checks it.

## Prerequisites

A session built on [`QtSession`][redsun.qt.QtSession], and a view whose
constructor starts with `(name: str, parent: QWidget)`. See
[Write a component](write-a-component.md).

## Put a widget in a dock or in the centre

Set `placement` on the class. [`Dock`][redsun.qt.Dock] takes the edge of the
window, `"left"`, `"right"`, `"top"` or `"bottom"`:

```python
from qtpy.QtWidgets import QWidget

from redsun import Placement
from redsun.qt import Central, Dock


class MyView(QWidget):
    placement: Placement = Dock("left")

    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.name = name


class ImageView(QWidget):
    placement: Placement = Central()

    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.name = name
```

The title of a dock is the name the view is declared under. When several
views ask for [`Central`][redsun.qt.Central], the centre shows them as tabs,
each titled with its view's name.

## Put an action in a menu or a toolbar

A view placed as a [`MenuItem`][redsun.qt.MenuItem] or a
[`ToolBarItem`][redsun.qt.ToolBarItem] is a `QAction`, with the same
constructor as any Qt view:

```python
from qtpy.QtGui import QAction
from qtpy.QtWidgets import QWidget

from redsun import Placement
from redsun.qt import MenuItem, ToolBarItem


class SnapAction(QAction):
    placement: Placement = MenuItem("Acquire")

    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__("Snap", parent)
        self.name = name


class StopAction(QAction):
    placement: Placement = ToolBarItem("Acquisition")

    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__("Stop", parent)
        self.name = name
```

`qtpy` exports `QAction` from `QtGui` only for the binding it selects, so
`mypy` needs the flags `qtpy mypy-args` prints, with `QT_API` set, to check a
class built on it.

The session creates the menu or toolbar the first time a view names it, and
adds every later view naming it to the same one. For a command that needs no
view of its own, see [Add menu actions](add-menu-actions.md).

## Place one view class in different places

A class attribute gives every instance the same placement. To choose it per
declaration, answer `placement` from a property and take the value as a
constructor keyword:

```python
from typing import Annotated

from qtpy.QtWidgets import QWidget

from redsun import AsView, Declare, Placement
from redsun.qt import Area, Dock, QtSession


class MyView(QWidget):
    def __init__(self, name: str, parent: QWidget, area: Area = "left") -> None:
        super().__init__(parent)
        self.name = name
        self.area = area

    @property
    def placement(self) -> Placement:
        return Dock(self.area)


class MyApp(QtSession):
    left_panel: AsView[MyView]
    right_panel: Annotated[AsView[MyView], Declare(area="right")]
```

A placement from a property is checked once the view is built rather than
when it is declared.

## See a changed placement take effect

A session started with `run` saves where the user left the docks when it
ends, and puts them back the next time. A dock that was saved keeps its
saved place, so a new placement for it does not show; a view under a name
not saved before takes its placement. To start every dock from its placement
again, close the session and remove the `window.state` key from its settings
file, listed in
[The session's settings](save-a-session.md#the-sessions-settings).

## Read a failure

A view that asks for a placement Qt does not show, or is not the type its
placement needs, is left out, and the build summary lists it under
`Not built`. Here `MyView`, a `QWidget`, asks for a `MenuItem`; the real
lines end with the file and line they were logged from:

```text
[29-09-26|08:42:44][ERROR]: Failed to build view 'snap': MyApp.snap asks to be attached as 'MenuItem', which needs a QAction, but MyView is not one
[29-09-26|08:42:44][WARNING]: Container built: 0/0 devices, 0/0 presenters, 0/1 views
Not built: snap (view)
```
