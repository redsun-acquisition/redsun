---
icon: lucide/monitor
---

# How a frontend shows a session on screen

A [frontend](glossary.md#frontend) is the part that shows your session to a
person: a desktop window today, and perhaps a web page in the future. `redsun`
ships one frontend, for Qt.

The core of `redsun` knows nothing about windows. It builds components and
connects them, and a frontend adds two things on top:

- a session class for you to subclass, such as
  [`QtSession`][redsun.qt.QtSession], which knows how to start the toolkit and
  put views on screen. It lives in the frontend's own package, `redsun.qt`,
  because importing it imports the toolkit, and a session without a window
  doesn't install the toolkit;
- a [`Frontend`][redsun.Frontend] class, which lists the
  [placements](glossary.md#placement) it can show.

## Placements

A view says where it wants to be shown, such as `Dock("left")`, `Central()` or
`MenuItem("File")`, and the frontend decides whether it can show it there.

The core defines only the `Placement` base class. Docks and menus belong to
windows, so the Qt frontend defines them, next to the code that shows them. In
`Frontend.requires`, a frontend lists what each placement must hold: Qt asks
for a `QWidget` in a dock or in the centre, and a `QAction` in a menu or
toolbar.

The session runs this check before it builds anything:

```text
Failed to build view 'stray': MyApp.stray asks to be attached as 'Route', which
Qt does not attach. It attaches: Central, Dock, MenuItem, ToolBarItem.
```

You can also give a `placement` in the declaration. The session then uses it
instead of the class's, and checks it the same way before anything is built.

!!! warning "A placement set from a property is checked late"

    A view that sets `placement` from a property is checked only once the view
    exists, since only the object can answer. That form is deprecated, so set
    `placement` as a plain class attribute or in the declaration instead.

A frontend also reads the `placement` words of a session file, with
`read_placement`. Qt, for example, turns `left` into a dock on the left and
`central` into the central area. The core of `redsun` knows none of these
words.

## The Qt frontend

A Qt view's constructor starts with `(name: str, parent: QWidget)`, written
exactly like that. `QtSession` passes its main window as the parent, so the
view is part of the window from the moment it exists. The session leaves out a
view whose constructor starts any other way, before it builds anything.
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
build without changing what it builds. The Qt frontend calls five
[hook points](glossary.md#hook-point), the named moments where a hook runs:

| point | called with | to |
| --- | --- | --- |
| `create_application` | the command-line arguments | make the `QApplication` yourself |
| `configure_application` | the `QApplication` | set a style or a font |
| `during_build` | the `QApplication` | show progress while the build runs |
| `configure_main_view` | the main window | change the window before it is shown |
| `confirm_close` | nothing | answer whether the window may close |

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

Presenters working on other threads call a view's
[slots](glossary.md#slot), but most toolkits let a view be used from one
thread only. A frontend settles that in three places:

| what | where | the Qt frontend |
| --- | --- | --- |
| the placements it shows | `Frontend.requires` | `Central`, `Dock`, `MenuItem`, `ToolBarItem` |
| the thread its views' slots run on | [`Frontend.thread_of`][redsun.Frontend.thread_of] | the main thread, for a `QWidget` |
| the delivery of the calls held for that thread | the session's `run` | `psygnal.qt.start_emitting_from_queue` |

The session asks `thread_of` only when neither the slot nor its class names a
thread. A call held for another thread waits in a queue until that thread
calls `psygnal.emit_queued`, so the session calls it from the toolkit's event
loop, as often as the views should follow the presenters.

Coroutine slots need nothing from the frontend, because every session sets the
backend that runs them when it starts its runtime. That's why a frontend's
`start_runtime` calls the one it overrides.
