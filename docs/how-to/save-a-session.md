---
icon: lucide/save
---

# How to save a session

A session keeps two kinds of state, and each is saved in its own place:

- The components and their settings make up what the session is. They live in
  the session file, and you can save a changed copy of it.
- How one person likes to run it, such as where they left the docks, their
  colour scheme and their answers to prompts, belongs to their machine. It
  lives in the session's settings.

## Let a component be saved

If the user can change a component while the session runs, define `serialize`
on it to say what it would be rebuilt with:

```python
class MotorPresenter:
    def __init__(self, name: str, *, step: float = 5.0) -> None:
        self.name = name
        self.step = step

    def serialize(self) -> dict[str, float]:
        return {"step": self.step}
```

The keys must be parameters of the constructor. If a key isn't one, the
session reports it and that component keeps the settings it was built with. A
component without `serialize` keeps them too.

## Save the configuration

Write what the session would now be rebuilt with to a new file:

```python
path = app.write("my-lab-2026-09.yaml")
```

[`write`][redsun.Session.write] saves one flat file, whatever the session was
built from, so the file opens on its own. It doesn't keep comments.

!!! warning "Overwriting a session file in use"

    Other sessions may read the same file, so `write` raises
    `ConfigurationInUse` if you write over a file the session was built from.
    Write to a new file name instead.

[`serialize`][redsun.Session.serialize] returns the same configuration as a
mapping, without writing it.

A Qt session also offers `Save configuration as...` in the menu `SAVE_MENU`,
under the command `<session name>.save_configuration`. To show that menu, see
[Add menu actions](add-menu-actions.md#show-the-menu).

## Decide what happens to unsaved changes

[`has_changes`][redsun.Session.has_changes] is true when any component would
now save different settings than it had at the end of the build. A value
changed and changed back counts as unchanged.

When you close the window with unsaved changes, a Qt session asks whether to
save, discard or cancel, and the prompt has a "don't ask again" box. To decide
yourself instead, install a `confirm_close` [hook](install-hooks.md).

## Find the settings file

[`Settings`][redsun.Settings] is one JSON file for each session name:

| platform | where a session called `my-lab` keeps it |
| --- | --- |
| Windows | `%LOCALAPPDATA%\redsun\my-lab.json` |
| Linux | `~/.config/redsun/my-lab.json` |
| macOS | `~/Library/Application Support/redsun/my-lab.json` |

A component or an action asks for it by type:

```python
from redsun import Settings


def forget_the_answer(settings: Settings) -> None:
    settings.set("ask_on_close", True)
```

The session writes a value as soon as it is set. The file appears the first
time something is set, and deleting it resets the session to its defaults. If
the file is damaged, the session ignores it and logs a warning.

A Qt session keeps these keys there itself:

| key | what it holds |
| --- | --- |
| `window.geometry`, `window.state`, `window.layout`, `window.center` | where the window and its docks were left, the layout they were left with, and how the centre's splitters and tabs were left |
| `ask_on_close` | whether the close prompt still appears |

A session started with `run` saves the window layout when it ends and puts it
back the next time, unless a view's placement has changed since. **Reset
layout** in the **Window** menu puts the docks back where their placements
say.

## Choose the colour scheme

A Qt session has a colour scheme button on its toolbar, which cycles through
system, light and dark. The session file chooses where it starts:

```yaml
color_scheme: dark
```
