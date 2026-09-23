---
icon: lucide/menu
---

# How to add menu actions to a Qt session

A Qt session can offer commands in its menus and toolbars without a view for
each: "turn on verbose logging", "open the data folder". You list them in the
`actions` section of the session file.

## Declare an action

Each entry takes the fields of an app-model `Action`:

```yaml
actions:
  - id: myapp.log.verbose
    title: Verbose logging
    callback: "mylab.contributions:enable_debug_logging"
    menus: [{ id: "myapp/settings" }]
```

- `id` names the command, and must be unique in the session.
- `title` is what the menu shows.
- `callback` is the function to run, written `module:function`.
- `menus` lists the menus the command appears in, by menu id.

The session reads the section while it builds, and registers every action on
the app-model `Application` it owns. Reading the section imports nothing: the
callback is imported the first time someone runs the command.

## Write the callback

A callback is an ordinary function. Its parameters are filled by type from
the same values the components were built from, so it can ask for the
session's [`Settings`][redsun.Settings], a
[shared value](../reference/glossary.md#shared-value), or the devices:

```python
# mylab/contributions.py
import logging

from redsun.log import set_level


def enable_debug_logging() -> None:
    set_level(logging.DEBUG)
```

## Show the menu

An action appears in a menu only when the window shows that menu. Show it
from a `configure_main_view` [hook](install-hooks.md), which receives the main
window:

```python
from app_model.backends.qt import QModelMainWindow

from redsun.qt import SAVE_MENU


class Menus:
    def configure_main_view(self, view: QModelMainWindow) -> None:
        view.setModelMenuBar({SAVE_MENU: "File", "myapp/settings": "Settings"})
```

The keys are menu ids, and the values are the titles shown.

`SAVE_MENU` is the menu `redsun` puts its own commands in, such as
`Save configuration as...`. Include it to offer them.

## Read a failure

A wrong entry raises `ActionError` from `redsun.qt` while the session builds,
naming the entry:

| message | cause |
| --- | --- |
| `actions section of MyApp must be a list of entries, ...` | `actions` is not a list |
| `actions entry at position 2 must be a mapping, ...` | an entry is not a mapping |
| `actions entry 'x' carries unknown key(s) ...` | a key app-model does not know, often a typo |
| `actions entry 'x' is not an action: ...` | app-model refused the values |
