---
icon: lucide/monitor
---

# How a frontend shows a session on screen

A [frontend](glossary.md#frontend) is what shows your session to a person: a
desktop window today, and perhaps a web page in the future. `redsun` ships one
frontend, for Qt.

The core of `redsun` knows nothing about windows. It builds components and
connects them, and a frontend adds two things on top:

- a session class for you to subclass, such as
  [`QtSession`][redsun.qt.QtSession], which knows how to start the
  [toolkit](glossary.md#toolkit) and put views on screen. It lives in the
  frontend's own package, `redsun.qt`, because importing it imports the
  toolkit, and a session without a window doesn't install the toolkit;
- a [`Frontend`][redsun.Frontend] class, which lists the
  [placements](glossary.md#placement) it can show.

## Placements

A view says where it wants to be shown, and the frontend decides whether it can
show it there. The core defines only the `Placement` base class. Docks and
menus belong to windows, so the Qt frontend defines them, next to the code that
shows them. Pick a placement to see where it puts a view, and point at it to
read what it needs:

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
scenarios: {
  dock: {
    window.dock_top.style.stroke-width: 4
    window.middle.dock_left.style.stroke-width: 4
    window.middle.dock_right.style.stroke-width: 4
    window.dock_bottom.style.stroke-width: 4
    window.menu.style.opacity: 0.3
    window.toolbar.style.opacity: 0.3
    window.middle.central.style.opacity: 0.3
  }
  central: {
    window.middle.central.style.stroke-width: 4
    window.menu.style.opacity: 0.3
    window.toolbar.style.opacity: 0.3
    window.dock_top.style.opacity: 0.3
    window.middle.dock_left.style.opacity: 0.3
    window.middle.dock_right.style.opacity: 0.3
    window.dock_bottom.style.opacity: 0.3
  }
  menu: {
    window.menu.style.stroke-width: 4
    window.toolbar.style.opacity: 0.3
    window.dock_top.style.opacity: 0.3
    window.middle.dock_left.style.opacity: 0.3
    window.middle.central.style.opacity: 0.3
    window.middle.dock_right.style.opacity: 0.3
    window.dock_bottom.style.opacity: 0.3
  }
  toolbar: {
    window.toolbar.style.stroke-width: 4
    window.menu.style.opacity: 0.3
    window.dock_top.style.opacity: 0.3
    window.middle.dock_left.style.opacity: 0.3
    window.middle.central.style.opacity: 0.3
    window.middle.dock_right.style.opacity: 0.3
    window.dock_bottom.style.opacity: 0.3
  }
}
```

In `Frontend.requires`, a frontend lists what each placement must hold: Qt asks
for a `QWidget` in a dock or in the centre, and a `QAction` in a menu or
toolbar.

### Checks before a build

The session checks every view before it builds anything. Step through the
checks:

```d2 title="What the session checks of a view"
...@diagrams/style
grid-rows: 2
grid-columns: 3
grid-gap: 60
placement: "which placement?" {class: step}
listed: "does the frontend\nshow it?" {class: step}
type: "is the view the\ntype it needs?" {class: step}
gap: {class: gap}
built: "build the view" {class: step}
constructor: "does the constructor\nstart right?" {class: step}
placement -> listed -> type -> constructor -> built
scenarios: {
  placement: {
    placement: {
      class: current
      tooltip: The placement given in the declaration, else the class's. A view class that names no placement is refused, since a component that is shown nowhere is a presenter.
    }
    listed.style.opacity: 0.3
    type.style.opacity: 0.3
    constructor.style.opacity: 0.3
    built.style.opacity: 0.3
  }
  listed: {
    listed: {
      class: current
      tooltip: The placement must be one the frontend lists in Frontend.requires. Qt lists Central, Dock, MenuItem and ToolBarItem.
    }
    placement.style.opacity: 0.3
    type.style.opacity: 0.3
    constructor.style.opacity: 0.3
    built.style.opacity: 0.3
  }
  type: {
    type: {
      class: current
      tooltip: Qt needs a QWidget in a dock or in the centre, and a QAction in a menu or a toolbar.
    }
    placement.style.opacity: 0.3
    listed.style.opacity: 0.3
    constructor.style.opacity: 0.3
    built.style.opacity: 0.3
  }
  constructor: {
    constructor: {
      class: current
      tooltip: "Frontend.check_view runs here. Qt asks for a constructor that starts with (name: str, parent: QWidget)."
    }
    placement.style.opacity: 0.3
    listed.style.opacity: 0.3
    type.style.opacity: 0.3
    built.style.opacity: 0.3
  }
}
```

A view that fails a check is left out before anything is built, with a message
naming what the frontend shows instead:

```text
Failed to build view 'stray': MyApp.stray asks to be attached as 'Route', which
Qt does not attach. It attaches: Central, Dock, MenuItem, ToolBarItem.
```

A view that sets `placement` from a property is checked only after the view
is built, since only the object can answer, so a placement the frontend can't
show fails that view only then. That form is deprecated and is removed in
0.16: set `placement` as a class attribute or in the declaration instead.

A frontend also reads the `placement` words of a session file, with
`read_placement`. Qt, for example, turns `left` into a dock on the left and
`central` into the central area. The core of `redsun` knows none of these
words.

## The Qt frontend

A Qt view's constructor starts with `(name: str, parent: QWidget)`, written
exactly like that. `QtSession` passes its main window as the parent, so the
view is part of the window from the moment it exists.
[How to place a view in the window](../how-to/place-a-view.md) shows the
constructor with each placement.

`QtSession` also:

- runs every slot of a widget on the main thread, unless the slot names
  another thread, because Qt widgets may only be used from there;
- keeps an `Application` from the `app-model` package for the session's menus
  and commands, and builds the main window from it;
- saves where the user left the docks, and puts them back the next time;
- asks before closing when a component has unsaved changes;
- logs any exception that no slot caught, with its traceback, and keeps the
  window open, where the Qt binding would otherwise end the process without a
  word;
- closes and deletes every view at shutdown, after delivering any signal still
  waiting for one. Closing runs each view's `closeEvent`, which is the only
  place a view that is a third-party widget can clean up, because it inherits
  its cleanup from the widget and has no `shutdown` of its own.

You choose the [Qt binding](glossary.md#qt-binding) with `QT_API`, which
`qtpy` reads. A session file never names one.

### Hook points

A [hook](glossary.md#hook) lets you act at fixed moments of a Qt session's
life, from making the application to closing the window, without changing
what the session builds. The Qt frontend calls five
[hook points](glossary.md#hook-point), the named moments where a hook runs.
Pick one to see when it runs, and point at it to read what it receives:

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
scenarios: {
  create_application: {
    create.class: current
    configure.style.opacity: 0.3
    during.style.opacity: 0.3
    main.style.opacity: 0.3
    close.style.opacity: 0.3
  }
  configure_application: {
    configure.class: current
    create.style.opacity: 0.3
    during.style.opacity: 0.3
    main.style.opacity: 0.3
    close.style.opacity: 0.3
  }
  during_build: {
    during.class: current
    create.style.opacity: 0.3
    configure.style.opacity: 0.3
    main.style.opacity: 0.3
    close.style.opacity: 0.3
  }
  configure_main_view: {
    main.class: current
    create.style.opacity: 0.3
    configure.style.opacity: 0.3
    during.style.opacity: 0.3
    close.style.opacity: 0.3
  }
  confirm_close: {
    close.class: current
    create.style.opacity: 0.3
    configure.style.opacity: 0.3
    during.style.opacity: 0.3
    main.style.opacity: 0.3
  }
}
```

[Install hooks](../how-to/install-hooks.md) shows how. A session with no
frontend calls no hook points, so it refuses a hook declared on it.

## Choosing the frontend from a file

A session file names its frontend by the name the frontend is registered
under:

```yaml
frontend: qt
```

`Session.from_config` reads that name and builds on the class registered under
it. Without a `frontend` key, it builds on the class you called `from_config`
on, which for a plain `Session` means no frontend at all.

Frontends are registered as entry points, the packaging feature that lets an
installed package announce what it offers, in the `redsun.frontends` group.
`redsun` registers its own there:

```toml
[project.entry-points."redsun.frontends"]
qt = "redsun.qt:QtSession"
```

A package that offers another frontend registers its session class the same
way, and a session file can then name it with no change to `redsun`. A
component that asks for [`SessionConfig`][redsun.SessionConfig] finds the
frontend's registered name in its `frontend` field, or `None` when the session
has no frontend.

## Writing a frontend

To show a session somewhere other than a desktop window, a frontend defines
its own placements, its own `Frontend` and a session class that shows the
views. [How to write a frontend](../how-to/write-a-frontend.md) writes one.
Two more methods let a frontend shape its views: `Frontend.check_view` refuses
a view class the frontend can't build, and `Session.view_arguments` adds
arguments to every view's constructor. Neither does anything unless a frontend
overrides it.

### What a frontend provides

A frontend provides three things: the placements it shows, the thread its
views' [slots](glossary.md#slot) run on, and the delivery of calls held for
that thread:

| what | where | the Qt frontend |
| --- | --- | --- |
| the placements it shows | `Frontend.requires` | `Central`, `Dock`, `MenuItem`, `ToolBarItem` |
| the thread its views' slots run on | [`Frontend.thread_of`][redsun.Frontend.thread_of] | the main thread, for a `QWidget` |
| the delivery of the calls held for that thread | the session's `run` | `psygnal.qt.start_emitting_from_queue` |

The last two matter because presenters working on other threads call a view's
slots, while most toolkits let a view be used from one thread only. Step
through a call from a presenter to a view:

```d2 title="A presenter calls a view from another thread"
...@diagrams/style
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
    queue: {
      class: current
      tooltip: The slot names no thread and neither does its class, so the session asks Frontend.thread_of, which answers the main thread for a QWidget.
    }
    (emit -> queue)[0].style.opacity: 1
  }
  2: {
    queue.class: step
    loop: {
      class: current
      tooltip: The session calls it from the toolkit's event loop, as often as the views should follow the presenters.
    }
    (queue -> loop)[0].style.opacity: 1
  }
  3: {
    loop.class: step
    slot.class: current
    (loop -> slot)[0].style.opacity: 1
  }
}
```

Coroutine slots need nothing from the frontend, because every session sets the
backend that runs them when it starts its runtime. That's why a frontend's
`start_runtime` must call the `start_runtime` it overrides.
