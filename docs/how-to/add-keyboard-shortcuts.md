---
icon: lucide/keyboard
---

# How to add keyboard shortcuts

A component runs one of its methods from a key once you mark the method with
[`shortcut`][redsun.shortcut]. The session binds the key when it builds, and
lists it under **Window** -> **Keyboard shortcuts**, where the user can change
it too.

## Mark a method

Put `@shortcut` on a method of a view or a presenter, with the key and a
title for the list:

```python
from redsun import shortcut


class MyView(QWidget):
    @shortcut("Ctrl+R", title="Run the selected plan")
    def run_selected(self) -> None: ...


class MyController:
    @shortcut("Escape", title="Stop the plan")
    def stop(self) -> None: ...
```

The method takes no arguments, since a key has none to give. Write the key
with `app-model`'s names, such as `Ctrl+Shift+R`, `F5`, `Escape` or
`Delete`. `Ctrl` is the Command key on macOS, so one key works everywhere;
give `mac=`, `win=` or `linux=` only when a platform needs a different one.
Don't write `Cmd` for Command: in `app-model`'s names, `Cmd` and `Meta` are
the Control key on macOS.

A method can be a [slot](../explanation/glossary.md#slot) and a shortcut at
once. A coroutine method can't be a shortcut yet, because a key fires on
Qt's thread while coroutines run on the session's own loop: call it from a
plain method instead.

## Keep a key to one view

A key marked `scope="view"` acts only while its view has focus, so it can
reuse a combination that already acts in the whole window:

```python
class MyView(QWidget):
    @shortcut("F5", title="Refresh", scope="view")
    def refresh(self) -> None: ...
```

While the view has focus, `F5` refreshes it; anywhere else it does what the
window binds it to. A presenter has nothing to focus, so its keys always act
in the whole window.

A text field with the focus keeps the keys it uses itself, such as `Ctrl+C`
and the arrow keys, so a shortcut on one of those keys doesn't act there.
Most other widgets give way. A tree, a tab bar, a slider or a button loses
its arrow keys to a shortcut, and a spin box loses `Up` and `Down`, so it no
longer steps. A view key on a bare arrow therefore takes the key from those
widgets in its own view, and a window key takes it from them everywhere. The
next section shows how to leave the key to them most of the time.

## Act only part of the time

A key can wait for a condition. Give `when=` a function of the component,
such as a method defined above the decorated one, and the key acts only
while that function returns true. The rest of the time the key does nothing,
so the key press goes to the widget that has focus:

```python
class MyView(QWidget):
    def _row_has_focus(self) -> bool: ...

    @shortcut("Left", title="Step back", scope="view", when=_row_has_focus)
    def step_back(self) -> None: ...
```

Here `Left` steps back while a row of the view has focus, and moves through
a tree or a tab bar of the same view the rest of the time. The session asks
the function each time the focus moves, not at each key press, so the method
still checks anything that can change while the focus stays put, such as
whether the row is locked.

## Change a key in the session file

The `shortcuts` section gives a command another key, two keys, or none. A
command is named after the component and the method:

```yaml
shortcuts:
  my_view.run_selected: Ctrl+Shift+R
  my_controller.stop: [Escape, Ctrl+.]
  my_view.step_back: null
```

The [session file reference](../reference/session-file.md#shortcuts) lists
the rules.

## Change a key in the window

The user changes keys in **Window** -> **Keyboard shortcuts**. Double-click a
key cell and press the new key; Backspace or Delete clears it. When another
command already has that key in the same place, the list asks "Already used
by *Run*; move it here?", and on yes the key moves and the other command is
left without it.

The session keeps these changes in its settings file, apart from the session
file, and applies them over the `shortcuts` section in every later run.
**Reset to defaults** forgets them, so the keys the components declare and
the session file gives come back.

## Read a conflict

Two components conflict when they ask for one key that acts in the same
place: both in the whole window, or both in one view. The first declared
keeps the key, and the log names both:

```text
Keyboard shortcuts:
  Ctrl+R: kept on my_view.run_selected, taken from my_controller.restart
```

Give one of them another key in the `shortcuts` section. With `strict: true`
in the session file, a conflict stops the build instead.
