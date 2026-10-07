---
icon: lucide/monitor
---

# How a frontend shows a session on screen

A [frontend](glossary.md#frontend) is what shows a session to a
person: a desktop window, and in the future perhaps a web page. `redsun` ships
one, for Qt.

The core of `redsun` knows nothing about windows. It builds components and
connects them. A frontend adds two things:

- a session class to subclass, such as [`QtSession`][redsun.qt.QtSession],
  which knows how to start the toolkit and put views on screen. It lives in
  the package of the frontend, `redsun.qt`, because importing it imports the
  toolkit, which a session without a window does not install;
- a [`Frontend`][redsun.Frontend] class, which lists the
  [placements](glossary.md#placement) it can show.

## Placements

A view says where it wants to be shown, such as `Dock("left")`,
`Central()` or `MenuItem("File")`, and the frontend decides whether it can.

The core defines only the `Placement` base class. Docks and menus are window
ideas, so the Qt frontend defines them, next to the code that shows them. A
frontend lists what each placement must be in `Frontend.requires`: Qt asks for
a `QWidget` in a dock or in the centre, and a `QAction` in a menu or toolbar.

The check happens before anything is built:

```text
Failed to build view 'stray': MyApp.stray asks to be attached as 'Route', which
Qt does not attach. It attaches: Central, Dock, MenuItem, ToolBarItem.
```

A declaration can give its own `placement`. The session then uses it
instead of the class's, and checks it the same way, before anything is built.
A view that sets `placement` from a property is checked only once it is made,
since only the object can answer. That form is deprecated.

A frontend also reads the `placement` words of a session file, with
`read_placement`. For example, Qt turns `left` into a dock on the left and
`central` into the central area. The core of `redsun` knows none of these
words.

## The Qt frontend

A Qt view's constructor starts with `(name: str, parent: QWidget)`, written
exactly like that. `QtSession` passes its main window as the parent, so a view
is part of the window from the moment it exists. A view whose constructor
starts differently is left out before anything is built.
[How to place a view in the window](../how-to/place-a-view.md) shows the
constructor with each placement.

`QtSession` also:

- runs every slot of a widget on the main thread, unless the slot names
  another, since Qt widgets may only be used from there;
- keeps an app-model `Application` for the session's menus and commands, and
  a main window built from it;
- saves where the user left the docks, and puts them back next time;
- asks before closing when a component has unsaved changes;
- logs an exception no slot caught, with its traceback, and keeps the window
  open, where the Qt binding would otherwise end the process without a word;
- closes and deletes every view at shutdown, delivering any signal still
  waiting for one first. Closing runs the `closeEvent` of each view, which is
  the only place a view that is a third-party widget can clean up: it
  inherits its cleanup from the widget, and has no `shutdown` of its own.

`QT_API` chooses the [Qt binding](glossary.md#qt-binding), as `qtpy` reads it.
A session file never names one.

### Hook points

A [hook](glossary.md#hook) lets you act at fixed moments of a
Qt session's build without changing what it builds. The Qt frontend calls five
[hook points](glossary.md#hook-point):

| point | called with | to |
| --- | --- | --- |
| `create_application` | the command-line arguments | make the `QApplication` yourself |
| `configure_application` | the `QApplication` | set a style or a font |
| `during_build` | the `QApplication` | show progress while the build runs |
| `configure_main_view` | the main window | change the window before it is shown |
| `confirm_close` | nothing | answer whether the window may close |

[Install hooks](../how-to/install-hooks.md) shows how. A session with no
frontend calls no hook points, so a hook declared on one is refused.

## Choosing the frontend from a file

A session file names its frontend by a registered name:

```yaml
frontend: qt
```

`Session.from_config` reads it and builds on the class registered under that
name. With no `frontend` key, it builds on the class `from_config` was called
on, which for a plain `Session` has no frontend at all.

Frontends are registered as entry points, in the `redsun.frontends` group.
`redsun` registers its own:

```toml
[project.entry-points."redsun.frontends"]
qt = "redsun.qt:QtSession"
```

A package offering another frontend registers its session class the same
way, and a session file can name it without `redsun` changing. A component
asking for [`SessionConfig`][redsun.SessionConfig] reads the frontend's
registered name from its `frontend` field, or `None` for a session with no
frontend.

## Writing a frontend

A frontend for something other than a desktop window defines its own
placements, its own `Frontend` and a session class that shows the views.
[How to write a frontend](../how-to/write-a-frontend.md) writes one.
`Frontend.check_view` refuses a view class the frontend cannot build, and
`Session.view_arguments` adds arguments to every view's constructor. Neither
does anything unless a frontend overrides it.

### What a frontend provides

A view's [slots](glossary.md#slot) are called by presenters
working on other threads, and most toolkits allow a view to be used from one
thread only. A frontend settles that in three places:

| what | where | the Qt frontend |
| --- | --- | --- |
| the placements it shows | `Frontend.requires` | `Central`, `Dock`, `MenuItem`, `ToolBarItem` |
| the thread its views' slots run on | [`Frontend.thread_of`][redsun.Frontend.thread_of] | the main thread, for a `QWidget` |
| the delivery of the calls held for that thread | the session's `run` | `psygnal.qt.start_emitting_from_queue` |

`thread_of` is asked only when neither the slot nor its class names a
thread. A call to a slot held for another thread waits in a queue until that
thread calls `psygnal.emit_queued`, so the session calls it from the
toolkit's event loop, as often as the views should follow the presenters.

Coroutine slots need nothing from the frontend: every session sets the
backend that runs them when it starts its runtime, which is why a frontend's
`start_runtime` calls the one it overrides.
