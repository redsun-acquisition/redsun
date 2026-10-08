---
icon: lucide/layout-dashboard
---

# How to place a view in the window

This page shows how to choose where a view of a Qt session appears: in a dock,
in the centre, in a menu or in a toolbar. Point at a part of the main window to
read what goes there:

```d2 title="Where each placement puts a view"
...@diagrams/style
window: "main window" {
  grid-rows: 5
  grid-gap: 10
  menu: "menu bar: MenuItem(\"Acquire\")" {
    class: step
    width: 520
    tooltip: The session creates the menu the first time a view names it, and adds every later view naming it to the same one.
  }
  toolbar: "toolbar: ToolBarItem(\"Acquisition\")" {
    class: step
    width: 520
    tooltip: The session creates the toolbar the first time a view names it, and adds every later view naming it to the same one.
  }
  top_dock: "Dock(\"top\")" {
    class: step
    width: 520
  }
  middle: "" {
    grid-columns: 3
    grid-gap: 10
    style.opacity: 0
    left_dock: "Dock(\"left\")" {class: step; height: 140}
    central: "Central()" {
      class: step
      width: 240
      tooltip: When several views ask for Central, the centre shows them as tabs, each titled with its view's name.
    }
    right_dock: "Dock(\"right\")" {
      class: step
      tooltip: Docks on the same edge with the same group open as tabs.
    }
  }
  bottom_dock: "Dock(\"bottom\")" {
    class: step
    width: 520
  }
}
```

[How a frontend shows a session on screen](../explanation/frontends.md)
explains what a [placement](../explanation/glossary.md#placement) is and how
a frontend checks it.

## Prerequisites

You need a session built on [`QtSession`][redsun.qt.QtSession], and a view
whose constructor starts with `(name: str, parent: QWidget)`. See
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
[`ToolBarItem`][redsun.qt.ToolBarItem] is a `QAction`, and it takes the same
constructor arguments as any Qt view:

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
adds every later view naming it to the same one. If the command needs no view
of its own, see [Add menu actions](add-menu-actions.md).

## Override a view's default placement

Every view class has a default place in the window, its `placement`. To put
a view somewhere else, give `placement` when you declare it, and the session
uses your value instead of the default. It doesn't pass `placement` to the
view, so this works for any view, including the built-in ones:

```python
from typing import Annotated

from redsun import AsView, Declare
from redsun.qt import Central, Dock, QtSession
from redsun.view.qt.builtins import LogView, PositionerView


class MyApp(QtSession):
    stage: Annotated[AsView[PositionerView], Declare(placement=Dock("left"))]
    log: Annotated[AsView[LogView], Declare(placement=Central())]
```

In a session file, write `placement` as a word or a short mapping:

```yaml
views:
  stage:
    plugin_name: redsun
    plugin_id: positioner
    placement: left
```

| `placement` | Where the view goes |
| --- | --- |
| `left`, `right`, `top`, `bottom` | a dock on that edge |
| `central` | the central area |
| `{dock: left, group: tools}` | a dock on that edge, in a tab with the other docks of group `tools` |
| `{menu: Acquire}` | an entry in the menu `Acquire` |
| `{toolbar: Acquisition}` | an entry in the toolbar `Acquisition` |

The session checks the placement before it builds anything, so if a view fails
to build, its error message appears where you placed it. The session refuses a
view whose constructor has its own `placement` parameter, because it keeps
that name for itself.

!!! warning "Deprecated: a `placement` property"

    Some views return `placement` from a property, to choose it per
    declaration. This still works, but it is deprecated and will be removed
    in 0.16. The session can read such a placement only after it builds the
    view, so it checks it late, and if the view fails to build, no error
    message appears in the window. Give `placement` in the declaration
    instead.

## Tab docks together

Docks on the same edge with the same group open as tabs. The tabs follow the
order you declare the views in:

```python
from typing import Annotated

from redsun import AsView, Declare
from redsun.qt import Dock, QtSession
from redsun.view.qt.builtins import LightView, PositionerView


class MyApp(QtSession):
    stage: Annotated[
        AsView[PositionerView], Declare(placement=Dock("right", group="hardware"))
    ]
    lights: Annotated[
        AsView[LightView], Declare(placement=Dock("right", group="hardware"))
    ]
```

## See a changed placement take effect

A session started with `run` saves where the user left the docks when it
ends, and puts them back the next time. So a dock that was saved stays where
the user left it, and a new placement for it doesn't show. Only a view whose
name wasn't saved before takes its placement. The log says which docks the
saved layout keeps away from their placement. To start every dock from its
placement again, close the session and remove the `window.state` key from its
settings file, as
[The session's settings](save-a-session.md#the-sessions-settings) describes.

## Read a failure

The session leaves out a view that asks for a placement Qt doesn't show, or
that isn't the type its placement needs, and the build summary lists it under
`Not built`. Here `MyView`, a `QWidget`, asks for a `MenuItem`; the real
lines end with the file and line they were logged from:

```text
[29-09-26|08:42:44][ERROR]: Failed to build view 'snap': MyApp.snap asks to be attached as 'MenuItem', which needs a QAction, but MyView is not one
[29-09-26|08:42:44][WARNING]: Session built: 0/0 devices, 0/0 presenters, 0/1 views
Not built: snap (view)
```
