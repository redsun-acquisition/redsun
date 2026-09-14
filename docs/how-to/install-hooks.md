# Install container hooks

A component acts for itself. A **hook** acts on the session's toolkit: it
supplies the application object, themes every window, or shows a splash screen
during the build. It is an ordinary object with no base class, and it never
changes what the container builds or in which order.

Each hook point is named after the method it calls, and a container installs
one provider per point. A provider is named in one of two places, and each
example below shows both. Picking a tab switches every tab on the site to the
same form.

=== "Container class"

    A container subclass declares a provider with
    [`declare_hook`][redsun.containers.components.declare_hook], under the
    attribute that names the point.

=== "Configuration file"

    A session declares a provider in the `hooks` section, under the point's
    name, with the provider's import path.

## Pick a hook point

| Point | Receives | Runs |
|---|---|---|
| `create_application` | `argv` | before anything else, and only when no `QApplication` exists yet |
| `configure_application` | the application | before the build constructs any view |
| `during_build` | the application | around the whole build, closing once the window is shown |
| `configure_main_view` | the main window | when the window is built, before it is shown |

Each point belongs to a toolkit, so all four are on
[`QtAppContainer`][redsun.qt.QtAppContainer]. A plain
[`AppContainer`][redsun.containers.container.AppContainer] calls none and
refuses them; a container for another toolkit declares that toolkit's points.

Each point has a protocol with its one method:
[`CreatesApplication`][redsun.containers._hooks.CreatesApplication],
[`ConfiguresApplication`][redsun.containers._hooks.ConfiguresApplication],
[`WrapsBuild`][redsun.containers._hooks.WrapsBuild] and
[`ConfiguresMainView`][redsun.containers._hooks.ConfiguresMainView]. A provider
implementing the method satisfies the protocol, with nothing to subclass or
register.

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

Annotate parameters with the toolkit alias, not the bare protocol, so a
provider for the wrong toolkit fails a type check instead of failing at
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

    `isinstance` does not accept a parameterised protocol, so the container
    checks the bare one. Only a type checker catches a provider for the wrong
    toolkit.

## Install it

=== "Container class"

    ```python
    from redsun.containers import declare_hook
    from redsun.qt import QtAppContainer


    class MyApp(QtAppContainer):
        configure_application = declare_hook(DarkTheme)
    ```

    A subclass inherits its bases' points and replaces one by declaring the
    same attribute.

=== "Configuration file"

    ```yaml
    schema_version: 1.0
    frontend: pyqt
    session: My session

    hooks:
      configure_application:
        provider: "mylab.theme:DarkTheme"
    ```

    The path is `module:ClassName`. Anything else is refused with
    `is not a class path`.

## Pass constructor arguments

=== "Container class"

    Keyword arguments go to the constructor; the provider is built when the
    container class is created:

    ```python
    class MyApp(QtAppContainer):
        configure_application = declare_hook(DarkTheme, accent="#d47f4c")
    ```

    Pass an object instead of a class to install one you built. Keyword
    arguments then raise `TypeError`, since nothing is left to construct:

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

    An entry takes only `provider` and `kwargs`, so a provider may have a
    constructor argument named `provider`.

## Serve more than one hook point

A provider keeping state between two points is installed at both as **one
object**, and the sharing is written out, not inferred.

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

    `&name` and `*name` are YAML anchors and aliases: an alias *is* the
    anchored node, so both keys hold one provider.

Two separate entries with the same provider and arguments are refused, since
the file cannot say whether they mean one shared object or two identical ones.
Give them different arguments to build two.

## Cover the build with a splash screen

`during_build` is a span, not a moment: it returns a context manager entered
before the first component is built and exited once the window is on screen.
What it yields is called with each step's name as the step starts.

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

Build the `QPixmap` in the constructor and check it. A missing file gives a
null `QPixmap` instead of raising, and `QSplashScreen` shows a null pixmap as a
0x0 window, so a mistyped path gives a splash that shows nothing.

The steps reported are
[`AppContainer.BUILD_STEPS`][redsun.containers.container.AppContainer.BUILD_STEPS]:
`services`, `virtual container`, `devices`, `connect`, `presenters`, `views`,
`providers`, `wiring` and `injection`, in that order. Size a display from that
tuple, not from your own count, which goes stale when the steps change.

The span exits through the context manager, so a build that raises still closes
the splash instead of leaving it over an application with no window. Anything
else surrounding the build belongs here too: a busy cursor, a profiler, a
logging context.

The span opens only in [`run`][redsun.qt.QtAppContainer.run]. `build` alone
reports nothing, which suits a test driving the container directly.

### Show progress

Each step is reported when it *starts*, so a bar counting finished steps sets
its value before advancing the count, and fills to the total after the `yield`
returns. Map step names to any wording:

```python
from functools import partial

from qtpy.QtCore import Qt
from qtpy.QtWidgets import QProgressBar

from redsun.containers import AppContainer

LABELS = {
    "services": "Starting services...",
    "virtual container": "Building virtual layer...",
    "devices": "Building devices...",
    "connect": "Connecting devices...",
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
`functools.partial` binds them into the `Callable[[str], None]` the container
expects. Only the count is instance state, since only the count must survive
between calls; the widgets belong to one span. Resetting `_done` when the span
opens, not only in `__init__`, lets one provider serve a container built twice.

The bar reaches the total only because it is filled after the `yield`: the
last step is announced when it begins, and nothing is reported when it ends.
Code after the `yield` runs only for a successful build, so a failed build
leaves the bar where it stopped and `finally` still closes the splash.

### Hand over to the window rather than closing

`close` dismisses the splash at once. Qt's handoff is
[`finish`](https://doc.qt.io/qt-6/qsplashscreen.html#finish), which keeps the
splash up until the given widget is displayed. A provider gets the window by
also serving `configure_main_view`, installed at both points as one object:

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

`configure_main_view` runs inside the span, so the window exists when the
splash is dismissed. It stays `None` if the build raises before the window
exists, hence the fallback.

`run` processes events once after showing the window and before exiting the
span, so the window has painted either way; `finish` also waits for it on
platforms where showing takes longer than one pass.

## Undo what a hook did

Add [`HasShutdown`][redsun.virtual.HasShutdown]'s `shutdown`. Hooks are shut
down after the presenters, in reverse order, and a provider serving several
points only once:

```python
class DarkTheme:
    def configure_application(self, app: QApplication) -> None:
        self._app = app
        self._previous = app.styleSheet()
        app.setStyleSheet(...)

    def shutdown(self) -> None:
        self._app.setStyleSheet(self._previous)
```

A `during_build` provider needs no `shutdown`: its context manager closes what
it opened. A failing `shutdown` is logged and the others still run.

## Read a failure

A wrong hook raises [`HookError`][redsun.containers.HookError], naming the
point.

=== "Container class"

    | Message | Cause |
    |---|---|
    | `MyApp declares a hook at 'x', which is not a hook point it calls; expected one of: ...` | the attribute name is not a point this container calls |
    | `hook provider 'X' declared at 'y' does not implement Z` | the method is missing or misspelled |
    | `cannot construct hook provider 'X' declared at 'y' with [...]` | the constructor rejected the keywords |
    | `TypeError: declare_hook takes keyword arguments only with a class` | keywords were passed with an already built provider |

    These are raised when the class body is read, so a mistake fails at import,
    not at build.

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

A point named on the container class *and* in the file raises
`hook point(s) 'x' are named both on MyApp and in the configuration`. Neither
wins: remove one.

## Related

- [Toolkit hook points](../explanation/decisions/0010-toolkit-hook-points.md)
  for why the points are what they are.
- [Wire components together](wire-components.md) for connecting components,
  which hooks do not do.
