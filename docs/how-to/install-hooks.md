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
the method the session calls on your provider. Some points take one
provider and others take several, as the table below says.

You can install a provider from the session class or from the session file.
Every example below shows both, as tabs, and picking a tab switches every tab
on the site to the same choice.

=== "Session class"

    Declare the provider with `AsHook`, as an attribute named after the hook
    point.

=== "Session file"

    Name the provider in the `hooks` section, under the name of the hook
    point, with the path to import it from, or with its short name when
    `redsun` ships it.

## Pick a hook point

| point | receives | runs | providers | protocol |
| --- | --- | --- | --- | --- |
| `create_application` | `argv` | first, and only when no `QApplication` exists yet | one | [`CreatesApplication`][redsun.CreatesApplication] |
| `configure_application` | the application | before any view is made | several | [`ConfiguresApplication`][redsun.ConfiguresApplication] |
| `during_build` | the application | around the build steps | several | [`WrapsBuild`][redsun.WrapsBuild] |
| `configure_main_view` | the main window | when the window is made, before it is shown | several | [`ConfiguresMainView`][redsun.ConfiguresMainView] |
| `confirm_close` | nothing | when the window is asked to close | one | [`ConfirmsClose`][redsun.ConfirmsClose] |

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

## Use a provider `redsun` ships

`redsun` ships providers you can install without writing your own. A session
file names one by a short name instead of a class path, and the
[session file reference](../reference/session-file.md#hooks) lists the names.
[Choose a style](choose-a-style.md) shows one of them in use.

=== "Session class"

    ```python
    from redsun.qt.styles.napari import NapariStyle


    class MyApp(QtSession):
        configure_application: AsHook[NapariStyle]
    ```

=== "Session file"

    ```yaml
    hooks:
      configure_application: napari
    ```

    The name alone is short for `provider: napari`, which you write out when
    you pass `kwargs`. A name stands for one hook point only, so writing the
    same name at two points is refused like two identical entries.

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

## Install several at one point

A point that takes several providers calls them one after another, so a style
and a provider of your own can both act on the application.

=== "Session class"

    The attribute named after the point declares one provider. Give every
    further one a name of its own and say which point it serves:

    ```python
    from typing import Annotated

    from redsun import AsHook, Serves
    from redsun.qt import QtHook, QtSession


    class MyApp(QtSession):
        configure_application: AsHook[DarkTheme]
        icon: Annotated[AsHook[AppIcon], Serves(QtHook.CONFIGURE_APPLICATION)]
    ```

=== "Session file"

    List the providers under the point:

    ```yaml
    hooks:
      configure_application:
        - provider: "mylab.theme:DarkTheme"
        - provider: "mylab.theme:AppIcon"
    ```

`AppIcon` here is a second provider with a `configure_application` method.
The providers of the class run first, in the order they are declared, and
then those of the file, in the order of the list. A point that takes one
provider refuses a second, wherever it was named.

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

The steps reported are the members of `BuildStep`, in order:

```python
from redsun.session import BuildStep
```

Size a progress bar from `len(BuildStep)` rather than counting by hand, so
it stays right when the steps change. Each step is reported when it starts,
so fill the bar to the end after the `yield`. The `finally` closes the splash
even when the build fails.

## Undo what a hook did

A provider puts back what it changed, so that nothing of it outlives the
session. Give it a `shutdown` method. The session calls it when it shuts
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

A provider that fails doesn't stop the session, but a mistake in how you
declared it does.

When a provider can't be built, or its hook method raises, the session logs
the error, skips the provider at every point it serves, and carries on. The
build summary lists it as `Hooks skipped: DarkTheme (configure_application)`,
and a skipped provider gets no `shutdown` call. A provider whose constructor
raised is logged as `cannot construct hook provider 'X' ...`.

Two cases stop the build instead. A `create_application` provider that
fails stops it, because the session can't run on another application. And
with `strict: true` in the session file, every skipped provider stops it.

A wrong declaration raises [`HookError`][redsun.HookError] and names the
point. In a session file, an entry of the wrong shape is found when the file
is read and raised as [`ConfigurationError`][redsun.ConfigurationError],
located as `hooks.<point>.<key>`.

| message | cause |
| --- | --- |
| `MyApp.x declares a hook at 'x', which is not a hook point MyApp calls; ...` | the attribute name is not a point this session calls |
| `hooks key 'x' is not a hook point MyApp calls; ...` | the same, in the file |
| `hook provider 'X' at 'y' does not implement Z` | the method is missing or misspelled |
| `the provider of 'create_application' failed, and a session does not start on another application: ...` | the provider of that point could not be built |
| `hooks.x.provider: Field required` | `provider` is missing from the file entry |
| `hooks.x.name: Extra inputs are not permitted` | an argument was written beside `provider` instead of under `kwargs` |
| `unknown hook provider 'x'; built-in names: ...` | the short name is not one `redsun` ships; check its spelling against the list |
| `hook provider 'p' is named twice, at 'a' and at 'b', with the same keys` | two identical entries; anchor one, or change the arguments |
| `hooks entry 'x' lists one provider twice` | one entry was aliased twice in the list of a point; list it once |
| `hook point 'x' takes one provider, and MyApp and its configuration name 2 between them` | the point takes one provider; remove all but one |

## See also

- [Hook points](../reference/hook-points.md) lists the points, the order
  providers run in, and what a provider owes the session.
- [Frontends](../explanation/frontends.md#hook-points) shows the points in
  the life of a Qt session.
- [ADR 10](../explanation/decisions/0010-toolkit-hook-points.md) records why
  the points are what they are, and
  [ADR 31](../explanation/decisions/0031-hook-points-take-several-providers.md)
  why a point takes several providers and a failing one is skipped.
- [Wire components together](wire-components.md) connects components, which
  hooks do not do.
