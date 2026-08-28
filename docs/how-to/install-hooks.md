# Install container hooks

A component acts on its own behalf. A **hook** acts on the application as a
whole: it themes every window, adds a step to the build, or reads the finished
session. It is an ordinary object, with no base class to inherit.

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
| `configure_build` | the container | before the first build phase |
| `configure_session` | the container | after the last build phase, with `is_built` set |
| `configure_main_view` | the main window | when the window is built, before it is shown |

`configure_build` and `configure_session` are toolkit-neutral and live on every
container. The other three are Qt points and exist only on
[`QtAppContainer`][redsun.qt.QtAppContainer]; naming one on a plain
[`AppContainer`][redsun.containers.container.AppContainer] is refused.

Each point has a protocol carrying its one method:
[`CreatesApplication`][redsun.containers._hooks.CreatesApplication],
[`ConfiguresApplication`][redsun.containers._hooks.ConfiguresApplication],
[`ConfiguresBuild`][redsun.containers.ConfiguresBuild],
[`ConfiguresSession`][redsun.containers.ConfiguresSession] and
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
[`QtConfiguresApplication`][redsun.containers.qt._hooks.QtConfiguresApplication]
and [`QtConfiguresMainView`][redsun.containers.qt._hooks.QtConfiguresMainView],
all exported from `redsun.qt`. The container points are
[`AppConfiguresBuild`][redsun.containers._hooks.AppConfiguresBuild] and
[`AppConfiguresSession`][redsun.containers._hooks.AppConfiguresSession].

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
    session: My session

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

## Add a step to the build

`configure_build` is the only point at which
[`register_phase`][redsun.containers.container.AppContainer.register_phase] and
[`unregister_phase`][redsun.containers.container.AppContainer.unregister_phase]
are legal. `after` is required, and names an existing phase:

```python
from redsun.containers import AppContainer


class Calibration:
    def __init__(self, passes: int = 1) -> None:
        self.passes = passes

    def configure_build(self, container: AppContainer) -> None:
        container.register_phase("calibrate", self._run, after="injection")

    def _run(self) -> None: ...
```

Read the sequence a container will run with
[`phases`][redsun.containers.container.AppContainer.phases]. The built-in phases
cannot be removed or reordered.

To watch the build rather than take part in it, connect to
[`sig_phase_complete`][redsun.containers.container.AppContainer.sig_phase_complete],
which carries the name of each phase as it finishes:

```python
class Splash:
    def configure_build(self, container: AppContainer) -> None:
        container.sig_phase_complete.connect(self._show)

    def _show(self, phase: str) -> None: ...
```

## Read the finished session

`configure_session` runs after the last phase with `is_built` already set, so
`devices`, `presenters` and `views` are readable:

```python
class Inventory:
    def configure_session(self, container: AppContainer) -> None:
        self.built = sorted(container.devices) + sorted(container.presenters)
```

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

A phase a hook registered is removed by the container itself, so a hook that
only calls `register_phase` needs no `shutdown`. A failing `shutdown` is logged
and does not stop the rest.

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

- [Container hooks and the build phase
  registry](../explanation/decisions/0008-container-hooks-and-the-phase-registry.md)
  for why the points are what they are.
- [Wire components together](wire-components.md) for connecting components,
  which hooks do not do.
