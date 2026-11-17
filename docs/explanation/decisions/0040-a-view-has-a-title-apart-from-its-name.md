# 40. A view has a title apart from its name

Date: 2026-11-17

## Status

Accepted

## Context

A view's declared name does two jobs. The session, the wiring and the session
file find the view by it, and Qt matches a dock to its place in a saved layout
by the dock's object name, which is the same name. Until now the window also
showed that name on the view's dock and tab, so a session read
`scan_commands` and `statistics_view` where a person expects "Commands" and
"Statistics". Renaming the view to fix the text would break the saved layouts
and every key that names it, and a session cannot rename a view class it
does not own, such as `redsun`'s own light view, at all.

## Decision

**A view has a title, the text the window shows for it, given the way its
placement is given.** A class sets its default as a class attribute, and a
declaration or the session file overrides it; a view with no title shows its
name. Before, the only way to change what a dock showed was to change the
name:

```python
# before
class MyApp(QtSession):
    commands: AsView[ScanCommands]  # the dock reads "commands"
```

After, the name stays and the title changes:

```python
# after
class ScanCommands(QWidget):
    placement: Placement = Dock("left")
    title = "Commands"


class MyApp(QtSession):
    lights: Annotated[AsView[LightView], Declare(title="Lasers")]
```

The session keeps `title` from the view's constructor, as it keeps
`placement`, and refuses a view whose constructor takes a `title` of its own.

The option weighed was the widget's own window title: the dock would show
`widget.windowTitle()` when the view sets one, and its name otherwise. That
needed no new keyword, but it exists only for a Qt widget, so another
[frontend](../glossary.md#frontend) could not show it, and a declaration could
not set it without reaching into the widget after it is built. The case that
decided it was the light view: a session that declares `redsun`'s light view
must be able to title it in the declaration, without a class of its own.

## Consequences

- The dock, the central tab, the Window menu and the keyboard shortcuts list
  show the title. The dock's object name stays the name, so layouts saved
  before titles existed keep loading.
- A view placed in a menu or a toolbar is an action showing its own text, so
  its title changes nothing there.
- `redsun`'s own views have titles, "Lights", "Log", "Positioner" and
  "Acquisition", so a session that declares them shows those texts.
- A view whose constructor took a `title` parameter is refused, and has to
  rename it.
- Two views may share a title, since nothing finds a view by it.
