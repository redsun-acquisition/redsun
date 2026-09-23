# Frontends

A [frontend](../reference/glossary.md#frontend) is what shows a session to a
person: a desktop window, and in the future perhaps a web page. `redsun` ships
one, for Qt.

The core of `redsun` knows nothing about windows. It builds components and
connects them. A frontend adds two things:

- a session class to subclass, such as [`QtSession`][redsun.qt.QtSession],
  which knows how to start the toolkit and put views on screen;
- a [`Frontend`][redsun.Frontend] class, which lists the
  [placements](../reference/glossary.md#placement) it can show.

## Placements

A view says where it wants to be shown, and the frontend decides whether it
can:

```python
from redsun import Placement
from redsun.qt import Central, Dock, MenuItem


class MotorView(QWidget):
    placement: Placement = Dock("left")


class ImageView(QWidget):
    placement: Placement = Central()


class SaveAction(QAction):
    placement: Placement = MenuItem("File")
```

The core defines only the `Placement` base class. Docks and menus are window
ideas, so the Qt frontend defines them, next to the code that shows them. A
frontend lists what each placement must be in `Frontend.requires`: Qt asks for
a `QWidget` in a dock or in the centre, and a `QAction` in a menu or toolbar.

The check happens before anything is built:

```text
Failed to build view 'stray': MyApp.stray asks to be attached as 'Route', which
Qt does not attach. It attaches: Central, Dock, MenuItem, ToolBarItem.
```

A view that sets `placement` from a property is checked as soon as it is
made, since only the object can answer.

## The Qt frontend

A Qt view's constructor starts with `(name: str, parent: QWidget)`, written
exactly like that. `QtSession` passes its main window as the parent, so a view
is part of the window from the moment it exists:

```python
class MotorView(QWidget):
    placement: Placement = Dock("left")

    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.name = name
```

A view whose constructor starts differently is left out before anything is
built.

`QtSession` also:

- runs every slot of a widget on the main thread, unless the slot names
  another, since Qt widgets may only be used from there;
- keeps an app-model `Application` for the session's menus and commands, and
  a main window built from it;
- saves where the user left the docks, and puts them back next time;
- asks before closing when a component has unsaved changes;
- closes and deletes every view at shutdown, delivering any signal still
  waiting for one first.

`QT_API` chooses the Qt binding, as `qtpy` reads it. A session file never names
one.

### Hook points

A [hook](../reference/glossary.md#hook) lets you act at fixed moments of a
Qt session's build without changing what it builds. The Qt frontend calls five
[hook points](../reference/glossary.md#hook-point):

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
placements and its own `Frontend`:

```python
from dataclasses import dataclass

from redsun import Frontend, Placement, Session


class Page:
    """What this frontend renders."""


@dataclass(frozen=True)
class Route(Placement):
    path: str


class Web(Frontend):
    requires = {Route: Page}


class WebSession(Session):
    frontend = Web

    def start_runtime(self) -> None: ...  # start the web server

    def present(self) -> None: ...  # serve each view at its route
```

`Frontend.check_view` refuses a view class the frontend cannot build, and
`Session.view_arguments` adds arguments to every view's constructor. Neither
does anything unless a frontend overrides it.
