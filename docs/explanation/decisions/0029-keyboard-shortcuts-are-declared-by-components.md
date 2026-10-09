# 29. Keyboard shortcuts are declared by components

Date: 2026-10-09

## Status

Accepted

## Context

No key was bound in a `redsun` window. The positioner stepped an axis on
Left and Right by reading key presses inside its widget, which nothing else
could see, list or change. A window built from several plugins needs more:
each component brings its own keys, two of them can ask for the same one,
and the user needs to see what's bound and, later, change it.

`napari`, which `redsun` may later bring in as a provider, keeps the keys of
its menu commands in `app-model` and its canvas keys in an older registry of
its own, and plans to move everything to `app-model`.

## Decision

- A component marks a method with `@shortcut(key, title=..., scope=...)`.
  The decorator only records the key on the method, as `@slot` does, so it
  lives in the core with no `app-model` import.
- A key is written in `app-model`'s spelling, where `Ctrl` is Command on
  macOS, with `mac=`, `win=` and `linux=` for a platform that differs.
- A key acts in the whole window. Marked `scope="view"`, it acts only while
  the component's view has focus. A presenter's keys always act in the
  whole window.
- Each shortcut is an `app-model` command named `<component>.<method>`, in
  the session's `Application`, beside the session file's actions.
- Keys are layered: what the component declares, then the session file's
  `shortcuts` section, then, in a later release, the user's own changes.
- When two commands ask for one key that acts in the same place, both in
  the whole window or both in one view, the first declared keeps it and the
  log names both. `strict` stops the build instead. A view may bind a
  combination the window binds too: while the view has focus, the view's
  binding acts.
- **Window** -> **Keyboard shortcuts** lists every key, grouped by view.

Other options were rejected:

- A table of keys on the class. The key would be written away from the
  method it runs, and a method name in a string goes stale.
- Components registering `app-model` actions themselves. Every component
  would depend on `app-model` and Qt, and the core couldn't check or list
  the keys.
- Refusing the build on any conflict. A shortcut shouldn't stop an
  instrument from starting.

### Before

```python
class MyView(QWidget):
    def keyPressEvent(self, event: QKeyEvent | None) -> None:
        if event is not None and event.key() == Qt.Key.Key_R:
            self.run_selected()
        else:
            super().keyPressEvent(event)
```

### After

```python
class MyView(QWidget):
    @shortcut("Ctrl+R", title="Run the selected plan")
    def run_selected(self) -> None: ...
```

The key now shows in the list, a session file can change it, and a second
component asking for it is caught when the session builds.

## Consequences

- A provider whose keys live in `app-model` can be listed beside the
  session's own.
- A coroutine method can't be a shortcut yet: a key fires on Qt's thread,
  while coroutines run on the session's own loop.
- Keys inside the built-in views, and changing keys in the list, come in
  later releases.
