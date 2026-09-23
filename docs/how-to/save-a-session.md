# Save a session

A session keeps two kinds of state:

- **What the session is**: its components and their settings. That is the
  session file, and you can save a changed copy of it.
- **How one person likes to run it**: where they left the docks, the colour
  scheme, an answer they gave a prompt. That belongs to their machine, in the
  session's settings.

## Let a component be saved

A component that the user can change while the session runs says what it
would be rebuilt with, by defining `serialize`:

```python
class MotorPresenter:
    def __init__(self, name: str, *, step: float = 5.0) -> None:
        self.name = name
        self.step = step

    def serialize(self) -> dict[str, float]:
        return {"step": self.step}
```

The keys must be parameters of the constructor. A key the constructor does not
take is reported, and that component keeps the settings it was built with. A
component without `serialize` also keeps them.

## Save the configuration

```python
path = app.write("my-lab-2026-09.yaml")
```

[`write`][redsun.Session.write] saves one flat file, whatever the session was
built from, so it opens on its own. Comments are not kept. Writing over a file
the session was built from raises `ConfigurationInUse`, since other sessions
may read that file too.

[`serialize`][redsun.Session.serialize] returns the same configuration as a
mapping, without writing it.

A Qt session also offers `Save configuration as...` in the menu `SAVE_MENU`,
under the command `<session name>.save_configuration`. See
[Add menu actions](add-menu-actions.md#show-the-menu) to show that menu.

## Unsaved changes

[`has_changes`][redsun.Session.has_changes] is true when any component would
now save different settings than it had at the end of the build. A value
changed and changed back counts as unchanged.

When the window is closed with unsaved changes, a Qt session asks whether to
save, discard, or cancel. The prompt has a "don't ask again" box. To decide
yourself instead, install a `confirm_close` [hook](install-hooks.md).

## The session's settings

[`Settings`][redsun.Settings] is one JSON file per session name:

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

A value is written as soon as it is set. The file appears the first time
something is set, and deleting it resets the session to its defaults. A
damaged file is ignored with a warning.

A Qt session keeps two keys there itself:

| key | what it holds |
| --- | --- |
| `window.geometry`, `window.state` | where the window and its docks were left |
| `ask_on_close` | whether the close prompt still appears |

The window layout is saved when a session started with `run` ends, and put
back the next time.

## The colour scheme

A Qt session has a colour scheme button on its toolbar, cycling system, light
and dark. The session file chooses where it starts:

```yaml
color_scheme: dark
```
