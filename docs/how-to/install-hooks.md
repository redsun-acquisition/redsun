# Install container hooks

A component acts on its own behalf. A **hook** acts on the toolkit the session
runs on: it supplies the application object, themes every window, or covers the
build with a splash screen. It is an ordinary object, with no base class to
inherit, and it never changes what the container builds or the order it builds
it in.

Each hook point is named by the method it calls, and a container installs one
provider per point. A provider is named in one of two places, and every example
below is shown in both. Picking a tab switches every other tab on this page, and
on any other page of this documentation, to the same form.

=== "Container class"

    A container subclass declares a provider with
    [`declare_hook`][redsun.containers.components.declare_hook], under the
    attribute that names the point.

=== "Configuration file"

    A session declares a provider under the `hooks` section, keyed by the same
    name, with the provider's import path.

## Pick a hook point

| Point | Receives | Runs |
|---|---|---|
| `create_application` | `argv` | before anything else, and only when no `QApplication` exists yet |
| `configure_application` | the application | before the build constructs any view |
| `during_build` | the application | around the whole build, closing once the window is shown |
| `configure_main_view` | the main window | when the window is built, before it is shown |

Every point belongs to a toolkit, so all four live on
[`QtAppContainer`][redsun.qt.QtAppContainer]. A plain
[`AppContainer`][redsun.containers.container.AppContainer] calls none, and
naming one on it is refused; a container for another toolkit declares the
moments that toolkit actually has.

Each point has a protocol carrying its one method:
[`CreatesApplication`][redsun.containers._hooks.CreatesApplication],
[`ConfiguresApplication`][redsun.containers._hooks.ConfiguresApplication],
[`WrapsBuild`][redsun.containers._hooks.WrapsBuild] and
[`ConfiguresMainView`][redsun.containers._hooks.ConfiguresMainView]. Implement
the method and the provider satisfies the protocol; there is nothing to
subclass and nothing to register.

## Write a provider

A class with the point's method on it:

```python
from qtpy.QtWidgets import QApplication


class DarkTheme:
    def __init__(self, accent: str = "#4c8eda") -> None:
        self.accent = accent

    def configure_application(self, app: QApplication) -> None:
        app.setStyleSheet(f"QWidget {{ background: #202020; color: {self.accent}; }}")
```

Type the parameter against the toolkit alias rather than the bare protocol, so
a provider written for the wrong toolkit fails a type check rather than at
runtime:

```python
from redsun.qt import QtConfiguresApplication


def takes_a_theme(provider: QtConfiguresApplication) -> None: ...
```

The aliases are [`QtCreatesApplication`][redsun.containers.qt._hooks.QtCreatesApplication],
[`QtConfiguresApplication`][redsun.containers.qt._hooks.QtConfiguresApplication],
[`QtWrapsBuild`][redsun.containers.qt._hooks.QtWrapsBuild] and
[`QtConfiguresMainView`][redsun.containers.qt._hooks.QtConfiguresMainView], all
exported from `redsun.qt`.

!!! note

    `isinstance` cannot be given a parameterised protocol, so the container
    checks the bare form. A provider built against the wrong toolkit is caught
    by a type checker, not by the build.

## Install it

=== "Container class"

    ```python
    from redsun.containers import declare_hook
    from redsun.qt import QtAppContainer


    class MyApp(QtAppContainer):
        configure_application = declare_hook(DarkTheme)
    ```

    A subclass inherits the points its bases declare, and may replace one by
    declaring the same attribute.

=== "Configuration file"

    ```yaml
    schema_version: 1.0
    frontend: pyqt
    name: My session

    hooks:
      configure_application:
        provider: "mylab.theme:DarkTheme"
    ```

    The path is `module:ClassName`. Anything else is refused with
    `is not a class path`.

## Pass constructor arguments

=== "Container class"

    Keyword arguments go to the constructor, and the provider is built as the
    container class is created:

    ```python
    class MyApp(QtAppContainer):
        configure_application = declare_hook(DarkTheme, accent="#d47f4c")
    ```

    Pass an object instead of a class to install one you built yourself. Keyword
    arguments are then a `TypeError`, since there is nothing left to construct:

    ```python
    theme = DarkTheme(accent="#d47f4c")


    class MyApp(QtAppContainer):
        configure_application = declare_hook(theme)
    ```

=== "Configuration file"

    Constructor arguments go under `kwargs`, never beside `provider`:

    ```yaml
    hooks:
      configure_application:
        provider: "mylab.theme:DarkTheme"
        kwargs:
          accent: "#d47f4c"
    ```

    An entry takes `provider` and `kwargs` and nothing else, so a provider is
    free to take a constructor argument of its own called `provider`.

## Serve more than one hook point

A provider holding state between two points is installed at both, as **one
object**. Sharing is written down rather than inferred.

=== "Container class"

    Bind the instance once and declare it twice:

    ```python
    theme = DarkTheme()


    class MyApp(QtAppContainer):
        configure_application = declare_hook(theme)
        configure_main_view = declare_hook(theme)
    ```

=== "Configuration file"

    Anchor the entry and alias it:

    ```yaml
    hooks:
      configure_application: &theme
        provider: "mylab.theme:DarkTheme"
        kwargs:
          accent: "#d47f4c"
      configure_main_view: *theme
    ```

    `&name` and `*name` are ordinary YAML anchors and aliases: an alias *is* the
    anchored node, so both keys hold one provider.

Two separate entries naming the same provider with the same arguments are
refused, because whether they mean one shared object or two identical ones
cannot be read off the file. Give them different arguments to build two.

## Cover the build with a splash screen

`during_build` is a span rather than a moment: it returns a context manager
entered before the first component is built and left once the window is on
screen. What the context manager yields is called with the name of each step as
it starts.

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

Build the `QPixmap` in the constructor and check it. `QPixmap` reports a
missing file by being null rather than by raising, and `QSplashScreen` given a
null pixmap is a window of size 0x0 - so a mistyped path produces a splash that
silently shows nothing.

The steps reported are
[`AppContainer.BUILD_STEPS`][redsun.containers.container.AppContainer.BUILD_STEPS]:
`virtual container`, `devices`, `presenters`, `views`, `providers`, `wiring`
and `injection`, in that order. Size a display from that tuple rather than from
a count of your own, which would drift the day the sequence changes.

The span is left through the context manager, so a build that raises closes the
splash on the way out rather than leaving it over an application that never got
a window. Anything else wanting to surround the build belongs here too: a busy
cursor, a profiler, a logging context.

The span opens only on [`run`][redsun.qt.QtAppContainer.run]. Calling `build` on
its own reports nothing, which is what a test driving the container directly
wants.

### Show progress

Each step is reported as it *starts*, so a bar showing how many are finished
sets the value before advancing its own count, and fills to the total after the
`yield` returns. Map the step names to whatever wording you want:

```python
from functools import partial

from qtpy.QtCore import Qt
from qtpy.QtWidgets import QProgressBar

from redsun.containers import AppContainer

LABELS = {
    "virtual container": "Building virtual layer...",
    "devices": "Connecting devices...",
    "presenters": "Starting presenters...",
    "views": "Laying out views...",
    "providers": "Registering providers...",
    "wiring": "Wiring signals...",
    "injection": "Injecting dependencies...",
}


class ProgressSplash:
    def __init__(self, image: str, labels: dict[str, str]) -> None:
        self.pixmap = QPixmap(image)
        if self.pixmap.isNull():
            raise ValueError(f"no image at {image!r}")
        self.labels = labels
        self._done = 0

    def report(
        self, screen: QSplashScreen, bar: QProgressBar, app: QApplication, step: str
    ) -> None:
        bar.setValue(self._done)
        screen.showMessage(
            self.labels.get(step, f"{step}..."), Qt.AlignmentFlag.AlignBottom
        )
        self._done += 1
        app.processEvents()

    @contextmanager
    def during_build(self, app: QApplication) -> Generator[Callable[[str], None]]:
        total = len(AppContainer.BUILD_STEPS)
        self._done = 0
        screen = QSplashScreen(self.pixmap)
        bar = QProgressBar(screen)
        bar.setRange(0, total)
        bar.setGeometry(0, self.pixmap.height() - 18, self.pixmap.width(), 18)
        screen.show()
        bar.show()
        app.processEvents()

        try:
            yield partial(self.report, screen, bar, app)
            bar.setValue(total)
            screen.showMessage("Ready", Qt.AlignmentFlag.AlignBottom)
            app.processEvents()
        finally:
            screen.close()
```

`report` is an ordinary method taking the widgets it draws on, and
`functools.partial` binds them to give the container the `Callable[[str], None]`
it expects. Only the count is instance state, because only the count has to
survive from one call to the next; the widgets belong to one span and stay
local to it. Resetting `_done` when the span opens rather than only in
`__init__` is what lets one provider serve a container that is built twice.

Filling the bar after the `yield` rather than inside `report` is what makes it
reach the total: the last step is announced when it begins, and nothing is
reported once it finishes. Statements after the `yield` run only on a build
that succeeded, so a failed build leaves the bar where it stopped and the
`finally` still closes the splash.

### Hand over to the window rather than closing

`close` dismisses the splash at once. Qt's own handoff is
[`finish`](https://doc.qt.io/qt-6/qsplashscreen.html#finish), which keeps the
splash up until the widget passed to it is displayed. A provider reaches the
window by serving `configure_main_view` as well, and is installed at both
points as one object:

```python
from qtpy.QtWidgets import QMainWindow


class Splash:
    def __init__(self, image: str) -> None:
        self.pixmap = QPixmap(image)
        if self.pixmap.isNull():
            raise ValueError(f"no image at {image!r}")
        self.window: QMainWindow | None = None

    def configure_main_view(self, view: QMainWindow) -> None:
        self.window = view

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
            if self.window is None:
                screen.close()
            else:
                screen.finish(self.window)
```

`configure_main_view` runs inside the span, before it is left, so the window is
there by the time the splash is dismissed. It stays `None` when the build
raises before the window exists, which is why the fallback is kept.

`run` processes events once after showing the window and before leaving the
span, so the window has painted either way; `finish` additionally waits for it
to be shown on platforms where that takes longer than one pass.

## Undo what a hook did

Add [`HasShutdown`][redsun.virtual.HasShutdown]'s `shutdown`. Hooks are torn
down after the presenters, in reverse order, and a provider serving several
points is torn down once:

```python
class DarkTheme:
    def configure_application(self, app: QApplication) -> None:
        self._app = app
        self._previous = app.styleSheet()
        app.setStyleSheet(...)

    def shutdown(self) -> None:
        self._app.setStyleSheet(self._previous)
```

A `during_build` provider needs no `shutdown`: its context manager already
closes what it opened. A failing `shutdown` is logged and does not stop the
rest.

## Read a failure

Every way of getting a hook wrong raises
[`HookError`][redsun.containers.HookError], naming the point.

=== "Container class"

    | Message | Cause |
    |---|---|
    | `MyApp declares a hook at 'x', which is not a hook point it calls; expected one of: ...` | the attribute name is not a point this container calls |
    | `hook provider 'X' declared at 'y' does not implement Z` | the method is missing or misspelled |
    | `cannot construct hook provider 'X' declared at 'y' with [...]` | the constructor rejected the keywords |
    | `TypeError: declare_hook takes keyword arguments only with a class` | keywords were passed with an already built provider |

    These are raised as the class body is read, so a mistake fails at import
    rather than at build.

=== "Configuration file"

    | Message | Cause |
    |---|---|
    | `hooks key 'x' is not a hook point AppContainer calls; expected one of: ...` | the key is not a point this container calls |
    | `hooks entry 'x' carries unknown key(s) ...` | a constructor argument was written beside `provider` instead of under `kwargs` |
    | `hooks entry 'x' must carry a string 'provider' naming a class as 'module:ClassName'` | `provider` is missing or is not a string |
    | `hook provider 'p' is not a class path; expected 'module:ClassName'` | the path has no `:` |
    | `cannot import hook provider 'p'` | the module or the attribute does not exist |
    | `hook provider 'p' names ..., which is not a class` | the path names a value, not a class |
    | `cannot construct hook provider 'p' with [...]` | the constructor rejected the `kwargs` |
    | `hook provider 'X' configured at 'y' does not implement Z` | the method is missing or misspelled |
    | `hook provider 'p' is named twice, at 'a' and at 'b', with the same keys` | two entries are indistinguishable; anchor one, or vary the arguments |

A point named on the container class *and* in the file is
`hook point(s) 'x' are named both on MyApp and in the configuration`. Neither
source wins: drop one.

## Related

- [Toolkit hook points](../explanation/decisions/0010-toolkit-hook-points.md)
  for why the points are what they are.
- [Wire components together](wire-components.md) for connecting components,
  which hooks do not do.
