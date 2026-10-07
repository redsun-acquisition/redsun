---
icon: lucide/anchor
---

# How to install hooks

A [hook](../explanation/glossary.md#hook) changes how the application itself
starts and looks, rather than what it contains. With a hook you can create the
Qt application object yourself, apply a style to every window, or show a
splash screen while the session builds. The class you write for this is called
a hook provider. It's an ordinary class, and it never changes which components
the session builds.

A hook acts at one of a fixed set of moments, called
[hook points](../explanation/glossary.md#hook-point). Each point is named after
the method the session calls on your provider, and a session has one provider
for each point at most.

You can install a provider from the session class or from the session file.
Every example below shows both, as tabs, and picking a tab switches every tab
on the site to the same choice.

=== "Session class"

    Declare the provider with `AsHook`, as an attribute named after the hook
    point.

=== "Session file"

    Name the provider in the `hooks` section, under the name of the hook
    point, with the path to import it from.

## Pick a hook point

| point | receives | runs | protocol |
| --- | --- | --- | --- |
| `create_application` | `argv` | first, and only when no `QApplication` exists yet | [`CreatesApplication`][redsun.CreatesApplication] |
| `configure_application` | the application | before any view is made | [`ConfiguresApplication`][redsun.ConfiguresApplication] |
| `during_build` | the application | around the build steps | [`WrapsBuild`][redsun.WrapsBuild] |
| `configure_main_view` | the main window | when the window is made, before it is shown | [`ConfiguresMainView`][redsun.ConfiguresMainView] |
| `confirm_close` | nothing | when the window is asked to close | [`ConfirmsClose`][redsun.ConfirmsClose] |

A provider serves a point by having the method of its protocol. It may
inherit from the protocol too, which lets a type checker hold it to the
signature.

All five belong to the Qt frontend, so they only work on a
[`QtSession`][redsun.qt.QtSession]. A plain [`Session`][redsun.Session] calls
no hook points and refuses a hook.

## Write a provider

A provider is a class with the point's method:

```python
from qtpy.QtWidgets import QApplication


class DarkTheme:
    def __init__(self, accent: str = "#4c8eda") -> None:
        self.accent = accent

    def configure_application(self, app: QApplication) -> None:
        app.setStyleSheet(f"QWidget {{ background: #202020; color: {self.accent}; }}")
```

It doesn't inherit from anything, because having the method is enough.

## Install it

=== "Session class"

    ```python
    from redsun import AsHook
    from redsun.qt import QtSession


    class MyApp(QtSession):
        configure_application: AsHook[DarkTheme]
    ```

    A subclass inherits its base's hooks, and replaces one by declaring the
    same attribute.

=== "Session file"

    ```yaml
    session: my-lab
    frontend: qt

    hooks:
      configure_application:
        provider: "mylab.theme:DarkTheme"
    ```

    The path is written `module:ClassName`.

## Pass constructor arguments

=== "Session class"

    ```python
    from typing import Annotated

    from redsun import AsHook, Declare


    class MyApp(QtSession):
        configure_application: Annotated[AsHook[DarkTheme], Declare(accent="#d47f4c")]
    ```

=== "Session file"

    Arguments go under `kwargs`, never beside `provider`:

    ```yaml
    hooks:
      configure_application:
        provider: "mylab.theme:DarkTheme"
        kwargs:
          accent: "#d47f4c"
    ```

## Serve more than one hook point

A provider that keeps something between two points is installed at both as
one object, so the state it keeps is shared.

=== "Session class"

    `Serves` lists the points, and the attribute name is then free:

    ```python
    from redsun import Serves
    from redsun.qt import QtHook


    class MyApp(QtSession):
        theme: Annotated[
            AsHook[DarkTheme],
            Serves(QtHook.CONFIGURE_APPLICATION, QtHook.CONFIGURE_MAIN_VIEW),
        ]
    ```

=== "Session file"

    Anchor the entry and alias it:

    ```yaml
    hooks:
      configure_application: &theme
        provider: "mylab.theme:DarkTheme"
      configure_main_view: *theme
    ```

    `&theme` names the entry and `*theme` reuses it, so both keys hold one
    provider. Two separate entries with the same provider and arguments are
    refused, since the file cannot say whether you meant one object or two.

## Show a splash screen during the build

`during_build` covers a span of time, not a moment, so it returns a context
manager that the session enters before the first build step and closes after
the last. The session calls what the manager yields with each step's name as
the step starts:

```python
from collections.abc import Callable, Generator
from contextlib import contextmanager

from qtpy.QtGui import QPixmap
from qtpy.QtWidgets import QApplication, QSplashScreen


class Splash:
    def __init__(self, image: str) -> None:
        self.pixmap = QPixmap(image)
        if self.pixmap.isNull():
            raise ValueError(f"no image at {image!r}")

    @contextmanager
    def during_build(self, app: QApplication) -> Generator[Callable[[str], None]]:
        screen = QSplashScreen(self.pixmap)
        screen.show()
        app.processEvents()

        def report(step: str) -> None:
            screen.showMessage(step)
            app.processEvents()

        try:
            yield report
        finally:
            screen.close()
```

Check the image in the constructor, because a missing file gives an empty
`QPixmap` instead of an error, and a splash that shows nothing.

The steps reported are those in `BUILD_STEPS`:

```python
from redsun.session import BUILD_STEPS
```

Size a progress bar from `len(BUILD_STEPS)` rather than counting by hand, so
it stays right when the steps change. Each step is reported when it starts,
so fill the bar to the end after the `yield`. The `finally` closes the splash
even when the build fails.

## Undo what a hook did

Give the provider a `shutdown` method. The session calls it when it shuts
down, once per provider however many points it serves, the last built first:

```python
class DarkTheme:
    def configure_application(self, app: QApplication) -> None:
        self._app = app
        self._previous = app.styleSheet()
        app.setStyleSheet("...")

    def shutdown(self) -> None:
        self._app.setStyleSheet(self._previous)
```

A `during_build` provider needs none: its context manager closes what it
opened.

## Read a failure

A wrong hook raises [`HookError`][redsun.HookError] and names the point. In a
session file, an entry of the wrong shape is found when the file is read and
raised as [`ConfigurationError`][redsun.ConfigurationError], located as
`hooks.<point>.<key>`.

| message | cause |
| --- | --- |
| `MyApp.x declares a hook at 'x', which is not a hook point MyApp calls; ...` | the attribute name is not a point this session calls |
| `hooks key 'x' is not a hook point MyApp calls; ...` | the same, in the file |
| `hook provider 'X' at 'y' does not implement Z` | the method is missing or misspelled |
| `cannot construct hook provider 'X' ...` | the constructor refused the arguments |
| `hooks.x.provider: Field required` | `provider` is missing from the file entry |
| `hooks.x.name: Extra inputs are not permitted` | an argument was written beside `provider` instead of under `kwargs` |
| `hook provider 'p' is named twice, at 'a' and at 'b', with the same keys` | two identical entries; anchor one, or change the arguments |
| `hook point(s) 'x' are named both on MyApp and in the configuration` | the class and the file both name the point; remove one |

## Related

- [Frontends](../explanation/frontends.md#hook-points) lists the points.
- [ADR 10](../explanation/decisions/0010-toolkit-hook-points.md) records why
  the points are what they are.
- [Wire components together](wire-components.md) connects components, which
  hooks do not do.
