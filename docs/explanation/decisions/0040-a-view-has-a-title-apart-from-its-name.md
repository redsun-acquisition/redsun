# 40. A view has a title apart from its name

Date: 2026-11-17

## Status

Accepted

## Context

A view's declared name does two jobs. The session, the wiring and the session
file find the view by it, and Qt matches a dock to its place in a saved layout
by the dock's object name, which is the same name. Until now the window also
showed that name on the view's dock and tab, so a session read `my_view`
where a person expects "Commands". Renaming the view to fix the text would break the saved layouts
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
    my_view: AsView[MyView]  # the dock reads "my_view"
```

After, the name stays and the title changes, given by the class or by the
declaration:

```python
# after
class MyView(QWidget):
    placement: Placement = Dock("left")
    title = "Commands"


class MyApp(QtSession):
    my_view: Annotated[AsView[MyView], Declare(title="Commands")]
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
- `redsun`'s own views have no title of their own, so a session declaring
  two of one kind still tells them apart by name. A session titles them in
  their declarations.
- A view whose constructor took a `title` parameter is refused, and has to
  rename it. A presenter or device given `title` in its declaration or
  session-file entry is refused too, where before the keyword reached its
  constructor.
- Two views may share a title, since nothing finds a view by it.
