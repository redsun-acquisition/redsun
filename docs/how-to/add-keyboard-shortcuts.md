---
icon: lucide/keyboard
---

# How to add keyboard shortcuts

A component runs one of its methods from a key once you mark the method with
[`shortcut`][redsun.shortcut]. The session binds the key when it builds, and
lists it under **Window** -> **Keyboard shortcuts**.

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
    @shortcut("Left", title="Step back", scope="view")
    def step_back(self) -> None: ...
```

While the view has focus, `Left` steps back; anywhere else it does what the
window binds it to. A presenter has nothing to focus, so its keys always act
in the whole window.

A text field with the focus keeps the keys it uses itself, such as `Ctrl+C`
and the arrow keys, so a shortcut on one of them doesn't act while a text
field has focus. Other widgets give way instead: a window shortcut on `Up`
takes the key from a focused spin box, which then doesn't step. Keep bare
arrow keys to a view's own shortcuts.

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
