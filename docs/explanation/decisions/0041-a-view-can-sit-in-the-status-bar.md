# 41. A view can sit in the status bar

Date: 2026-11-19

## Status

Accepted

## Context

A Qt session places a view in a dock, in the centre, in a menu or in a
toolbar. Some views belong in none of these. A row of labels showing the
cursor position or the state of a device is read at a glance while the rest
of the window is in use, and a person looks for it in the status bar at the
bottom of the main window.

Without a placement for the status bar, such a view had to be declared
somewhere else and reach the status bar itself. A docked view found its main
window when it was first shown and added its labels there:

```python
# before
class StatusView(QWidget):
    placement: Placement = Dock("right")

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        window = self.window()
        if isinstance(window, QMainWindow):
            for label in self.labels:
                window.statusBar().addPermanentWidget(label)
```

The labels then existed only while that dock did, and the view had to take
them out of the status bar again when it was shut down.

## Decision

**`StatusBarItem` places a view's widget at the right of the main window's
status bar.** The session adds it as a permanent widget, so a message shown
in the status bar never covers it:

```python
# after
class StatusView(QWidget):
    placement: Placement = StatusBarItem()
```

In a session file the placement is the word `status_bar`. Several views
asking for it sit in the order they are declared, followed by what the
`configure_main_view` hook adds and, last, the button listing the
components that failed.

The placement has no fields. These options were weighed and left out:

- A stretch factor, so a view could take the width the status bar has
  spare. No view asked for it, and the spare width is where the status bar
  shows its messages.
- Starting hidden, and an entry in the Window menu to show the view again.
  The status bar is not a region of the window layout, so `hidden` would
  need a rule of its own, and no view asked to be hidden.
- Messages posted through the session. No component asked for it, so the
  status bar's message area stays as Qt provides it, and nothing in `redsun`
  writes to it.

## Consequences

- A view placed in the status bar is a `QWidget`, as in a dock or the
  centre.
- The widget keeps the width its size hint gives it. A view whose text
  changes length sets its own width, or the widgets to its left move at
  each update.
- A window layout naming such a view leaves it out with a warning, as it
  does for a menu or toolbar item, and the Window menu does not list it.
- A view in the status bar that fails to build gets no placeholder there;
  the button listing the failed components names it.
