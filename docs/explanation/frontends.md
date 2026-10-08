---
icon: lucide/monitor
---

# How a frontend shows a session on screen

A [frontend](glossary.md#frontend) is what shows your session to a person: a
desktop window today, and perhaps a web page in the future. `redsun` ships one
frontend, for Qt.

The core of `redsun` knows nothing about windows. A frontend adds a session
class to subclass, such as [`QtSession`][redsun.qt.QtSession], which starts
the [toolkit](glossary.md#toolkit) and shows the views, and a
[`Frontend`][redsun.Frontend] listing the [placements](glossary.md#placement)
it can show. `QtSession` lives in `redsun.qt` because importing it imports the
toolkit, which a session without a window doesn't install.

## Placements

A view says where it wants to be shown, and the frontend decides whether it
can. The core defines only the `Placement` base class; the Qt frontend defines
docks and menus. Point at a placement to read what it needs:

```d2 title="Where Qt puts a view"
...@diagrams/style
vars: {
  dock: "Holds a QWidget, in a dock against that edge. Docks given the same group on one edge are tabbed together. In a session file: left, right, top, bottom, or {dock: left, group: name}."
}
window: "main window" {
  grid-rows: 5
  grid-gap: 12
  menu: "MenuItem(\"File\")\nan entry in the File menu" {
    class: step
    tooltip: "Holds a QAction. The menu is made if the window has none of that name. In a session file: {menu: File}."
  }
  toolbar: "ToolBarItem(\"Main\")\nan entry in the Main toolbar" {
    class: step
    tooltip: "Holds a QAction. The toolbar is made if the window has none of that name. In a session file: {toolbar: Main}."
  }
  dock_top: 'Dock("top")' {
    class: step
    tooltip: ${dock}
  }
  middle: "" {
    grid-columns: 3
    grid-gap: 12
    style.opacity: 0
    dock_left: 'Dock("left")' {
      class: step
      tooltip: ${dock}
    }
    central: "Central()\nthe main area" {
      class: step
      tooltip: "Holds a QWidget. When several views ask for it, each gets a tab. In a session file: central."
    }
    dock_right: 'Dock("right")' {
      class: step
      tooltip: ${dock}
    }
  }
  dock_bottom: 'Dock("bottom")' {
    class: step
    tooltip: ${dock}
  }
}
```

In `Frontend.requires`, a frontend lists what each placement must hold: Qt asks
for a `QWidget` in a dock or in the centre, and a `QAction` in a menu or
toolbar.

### Checks before a build

The session checks every view before it builds anything; point at a check to
read what it asks:

```d2 title="What the session checks of a view"
...@diagrams/style
grid-rows: 2
grid-columns: 3
grid-gap: 60
placement: "which placement?" {
  class: step
  tooltip: The placement given in the declaration, else the class's. A view class that names no placement is refused, since a component that is shown nowhere is a presenter.
}
listed: "does the frontend\nshow it?" {
  class: step
  tooltip: The placement must be one the frontend lists in Frontend.requires. Qt lists Central, Dock, MenuItem and ToolBarItem.
}
type: "is the view the\ntype it needs?" {
  class: step
  tooltip: Qt needs a QWidget in a dock or in the centre, and a QAction in a menu or a toolbar.
}
gap: {class: gap}
built: "build the view" {class: current}
constructor: "does the constructor\nstart right?" {
  class: step
  tooltip: "Frontend.check_view runs here. Qt asks for a constructor that starts with (name: str, parent: QWidget)."
}
placement -> listed -> type -> constructor -> built
```

A view that fails a check is left out before anything is built, with a message
naming what the frontend shows instead:

```text
Failed to build view 'stray': MyApp.stray asks to be attached as 'Route', which
Qt does not attach. It attaches: Central, Dock, MenuItem, ToolBarItem.
```

A `placement` set from a property can only be checked after the view is
built; that form is deprecated and goes in 0.16, so set it as a class
attribute or in the declaration. A session file's placement words, such as
`left` or `central`, are read by the frontend's `read_placement`; the core
knows none of them.

## The Qt frontend

A Qt view's constructor starts with exactly `(name: str, parent: QWidget)`,
and `QtSession` passes its main window as the parent
([How to place a view](../how-to/place-a-view.md)). `QtSession` also:

- runs a widget's slots on the main thread unless a slot names another
- builds the main window from an `app-model` `Application` holding the menus
  and commands
- restores the docks where the user left them, until a placement changes,
  and has a Window menu to show a closed dock or reset the layout
- asks before closing when a component has unsaved changes
- logs an exception no slot caught and keeps the window open, where the Qt
  binding would end the process silently
- closes and deletes every view at shutdown, after delivering waiting
  signals, so a third-party widget can clean up in its `closeEvent`

The [Qt binding](glossary.md#qt-binding) is chosen with `QT_API`, read by
`qtpy`, never by a session file.

### Hook points

A [hook](glossary.md#hook) acts at a fixed moment of a Qt session's life
without changing what the session builds. The five
[hook points](glossary.md#hook-point) run in this order; point at one to read
what it receives:

```d2 title="The hook points of a Qt session"
...@diagrams/style
grid-rows: 2
grid-columns: 3
grid-gap: 60
create: "create_application\nmake the QApplication\nyourself" {
  class: step
  tooltip: Called with the command-line arguments, when no QApplication exists yet. It returns the QApplication.
}
configure: "configure_application\nset a style or a font" {
  class: step
  tooltip: Called with the QApplication, before any view is made.
}
during: "during_build\nshow progress while\nthe build runs" {
  class: step
  tooltip: Called with the QApplication. It wraps the build steps, from services to report.
}
close: "confirm_close\nanswer whether the\nwindow may close" {
  class: step
  tooltip: Called with nothing, when the window is asked to close. It answers in place of the question about unsaved changes.
}
shown: "the window is shown\nand the event loop runs" {class: note}
main: "configure_main_view\nchange the window\nbefore it is shown" {
  class: step
  tooltip: Called with the main window, in the presentation step, once the views are in place.
}
create -> configure -> during -> main -> shown -> close
```

[Install hooks](../how-to/install-hooks.md) shows how. A session with no
frontend calls no hook points, so it refuses a hook declared on it.

## Choosing the frontend from a file

A session file names its frontend by the name the frontend is registered
under:

```yaml
frontend: qt
```

`Session.from_config` builds on the class registered under that name, or,
without a `frontend` key, on the class you called it on. Frontends are
registered as entry points, the packaging feature through which an installed
package announces what it offers, in the `redsun.frontends` group:

```toml
[project.entry-points."redsun.frontends"]
qt = "redsun.qt:QtSession"
```

Another package registers its session class the same way, with no change to
`redsun`. A component asking for [`SessionConfig`][redsun.SessionConfig]
finds the registered name in its `frontend` field, or `None`.

## Writing a frontend

A new frontend defines its placements, its `Frontend` and a session class
that shows the views ([How to write a frontend](../how-to/write-a-frontend.md)).
It may override `Frontend.check_view`, to refuse a view class it can't build,
and `Session.view_arguments`, to add arguments to every view's constructor.

### What a frontend provides

| what | where | the Qt frontend |
| --- | --- | --- |
| the placements it shows | `Frontend.requires` | `Central`, `Dock`, `MenuItem`, `ToolBarItem` |
| the thread its views' slots run on | [`Frontend.thread_of`][redsun.Frontend.thread_of] | the main thread, for a `QWidget` |
| the delivery of the calls held for that thread | the session's `run` | `psygnal.qt.start_emitting_from_queue` |

The thread and the delivery matter because presenters on other threads call a
view's [slots](glossary.md#slot), while most toolkits allow one thread only.
Step through such a call:

```d2 title="A presenter calls a view from another thread"
...@diagrams/style
label: "A presenter working on a worker thread emits a signal connected to a view's slot."
grid-rows: 2
grid-columns: 2
grid-gap: 60
emit: "presenter emits\non a worker thread" {class: step}
queue: "the call waits\nin a queue" {class: hidden}
slot: "the view's slot runs\non the main thread" {class: hidden}
loop: "the event loop calls\npsygnal.emit_queued" {class: hidden}
emit -> queue: {class: hidden}
queue -> loop: {class: hidden}
loop -> slot: {class: hidden}
steps: {
  1: {
    label: "The slot names no thread and neither does its class, so the session asks Frontend.thread_of, which answers the main thread for a QWidget. The call waits in a queue."
    queue: {
      class: current
      tooltip: The slot names no thread and neither does its class, so the session asks Frontend.thread_of, which answers the main thread for a QWidget.
    }
    (emit -> queue)[0].style.opacity: 1
  }
  2: {
    label: "The session calls psygnal.emit_queued from the toolkit's event loop, as often as the views should follow the presenters."
    queue.class: step
    loop: {
      class: current
      tooltip: The session calls it from the toolkit's event loop, as often as the views should follow the presenters.
    }
    (queue -> loop)[0].style.opacity: 1
  }
  3: {
    label: "The queued call runs, and the view's slot runs on the main thread, where Qt allows it."
    loop.class: step
    slot.class: current
    (loop -> slot)[0].style.opacity: 1
  }
}
```

Coroutine slots need nothing from the frontend, because every session sets the
backend that runs them when it starts its runtime. That's why a frontend's
`start_runtime` must call the `start_runtime` it overrides.
