# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Dates are specified in the format `DD-MM-YYYY`.

## [Unreleased]

### Added

- `redsun.experimental` - a container layer built on
  [dishka](https://dishka.readthedocs.io), behind the `experimental` extra.
  **Not covered by any stability guarantee**: names and behaviour may change or
  be withdrawn in any release. `redsun.containers` remains the supported layer.

  Components are declared as annotations rather than `declare_*` calls, each
  naming the layer it belongs to, and a component's collaborators are
  constructor parameters resolved by type:

  ```python
  class MyApp(QtAppContainer):
      config = "session.yaml"

      stage: AsDevice[MyStage]
      motor_ctrl: AsPresenter[MotorPresenter]
      motor_widget: Annotated[AsView[MotorView], Declare(step_size=5.0)]
  ```

  `AsDevice`, `AsPresenter` and `AsView` wrap the component's own type without
  replacing it, so the attribute stays typed as what it holds. One of them is
  required: it is what marks an annotation as a component, so a container class
  may hold ordinary attributes beside its components, and the layer is stated
  rather than inferred from the class. It is checked when the declarations are
  read. A device must subclass `ophyd_async.core.Device`, and a class that
  subclasses it is refused in either other layer before anything else about it
  is considered. A presenter or view must take `name` as its first parameter,
  positionally or as a keyword, so a pydantic model whose fields are all
  keyword-only can be a presenter; a name that could only arrive inside
  `*args` or `**kwargs` is refused. Devices
  are therefore still built before the graph runs. A component appearing only in
  the session file takes its layer from the section it sits under, and is
  checked the same way. The three are also reachable as
  `redsun.experimental.containers.components`.

  The attribute name is both the component name and its configuration key;
  `Alias` and `FromConfig` override each. `provides` marks a method whose
  return value other components may ask for, replacing `register_providers`.
  A parameter annotated `X | None` is `None` when nothing supplies `X`,
  replacing `try_require`. A parameter carrying a default keeps it when the
  session provides neither a value nor a configuration entry for it, so a
  tunable does not have to be repeated in the configuration file to be
  constructible. `IsProvider`, `IsInjectable`, `ProviderKey` and the
  `provide`/`require` pair have no equivalent and are not needed, and
  `VirtualContainer` itself is not among the types a component may ask for: a
  component names the values it needs, not the session that holds them.

  Build order is derived from the dependency graph rather than fixed phases.
  `BlueskyCallbackRegistry` is the callback registry as a component sees it,
  and it is a live view rather than a snapshot. A component registers its own
  callbacks through `BlueskyCallbackRegistry.register` while it is built, and
  holds the view to read once the application is, so consuming the registry
  carries no ordering constraint. Reading it during construction raises
  `LookupError`, because the answer would be incomplete.

  ```python
  from redsun.experimental import BlueskyCallbackRegistry


  class MyPresenter:
      def __init__(self, name: str, /, callbacks: BlueskyCallbackRegistry) -> None:
          self.name = name
          callbacks.register(self, name=name)
  ```

  `Requires[P]` asks the session which of its components satisfy a protocol,
  instead of asking for one value. It is spelled
  `Annotated[Mapping[str, P], Every()]`, so the parameter is an ordinary mapping
  of names to components, and it is a live view for the same reason
  `BlueskyCallbackRegistry` is. A component satisfying *P* appears in its own
  answer.

  `RequiresOne[P]` and `RequiresMaybe[P]` ask the same question expecting a
  single answer, and are ordinary dependencies rather than live views: the
  component arrives built, and whatever answers is constructed first. Which
  component answers is settled before anything is built, so a session holding
  none (`RequiresOne`) or more than one fails to build, naming the components
  that nearly matched and why. `RequiresMaybe` answers `None` for an empty
  session. Both require *P* to declare at least one method, because a member
  assigned in `__init__` cannot be seen that early; it is confirmed once the
  instance exists.

  `DevicesOf[P]` asks the same question of the devices, which `Requires[P]`
  never answers over. It is spelled `Annotated[Mapping[str, P], Devices()]`, and
  unlike the component census it is not a live view: devices exist before any
  component is built, so the mapping arrives complete and may be read in
  `__init__`. Ask for `DeviceMapping` to receive every device unfiltered.

  Membership is decided structurally rather than with `isinstance`: an
  implementation must accept every call the protocol permits, so a renamed
  parameter or an extra required one is no longer a match, while an extra
  defaulted parameter still is. Types are not compared, which a type checker
  does at the call site. `satisfies` exposes the same check, and
  `Satisfying.rejected` reports why each near miss was left out. *P* must still
  be `runtime_checkable`, which is how a protocol declares it is meant to be
  matched at runtime.

  A container names its toolkit by subclassing, as `redsun.experimental.containers.qt`'s
  `QtAppContainer` does; `AppContainer.frontend` is a class attribute, and
  `AppContainer` on its own names no toolkit and accepts any placement. The base
  container builds the components and the toolkit one arranges them:
  `QtAppContainer.__init__` puts a `QApplication`, the async backend and an empty
  `QMainWindow` in place, since a widget cannot be built before any of them
  exist; `build` builds and attaches the views to that window, exposed as
  `main_window`; `run` shows it and hands over to the event loop. A component may
  not be named after something the container already answers, such as `devices`
  or `run`, since it could never be read back.

  Layers are a build order, so a component may depend on its own layer or an
  earlier one and never on a later one. Two views sharing a value is therefore
  allowed and needs no publish-then-resolve pass: one shares it with `provides`,
  the other asks for it in `__init__`, and the owner is built first because the
  graph says so. A presenter naming a view, or a type only a view shares, is
  refused before anything is constructed, naming both components and both
  layers. `Requires[P]` is exempt: it is a live view of the session rather than
  a dependency.

  `AppContainer.from_config` returns a container for a session described by a
  file or a mapping, for a session with no class of its own to declare anything.
  The `frontend:` key picks the container to build on, so a session naming `pyqt`
  comes up on `QtAppContainer` without importing it, and one naming a frontend
  the class it was called on is not built against is refused rather than ignored.
  Calling it on a class keeps that class's own declarations, its `wire` and its
  toolkit, and what comes back is unbuilt, so whatever the file cannot say is
  still said in Python before `build` runs. `AppContainer()` also takes the
  session directly, overriding the `config` class attribute for that instance
  alone.

  A view declares the `Placement` it asks the frontend to attach it at, which is
  what separates it from a presenter. The core defines `Placement` and no
  concrete one: a dock, a menu bar and a toolbar are window concepts, so
  `redsun.experimental.containers.qt` owns `Dock`, `Central`, `MenuItem` and `ToolBarItem`
  alongside the `Qt` frontend that pairs each with the toolkit type it demands
  in `Frontend.requires` - a `QWidget` for a dock or the centre, a `QAction` for
  a menu or toolbar entry - and the `attach` that fills a `QMainWindow` from a
  container's `views`. No toolkit name reaches the core, and a frontend for
  something other than a desktop window brings placements and a table of its
  own:

  ```python
  from redsun.experimental import Frontend


  class Web(Frontend):
      requires = {Route: Page}
  ```

  `Frontend.check_placement` reads that table and is what a frontend overrides
  when its demand is not a subclass relation. Declaring the placement on the
  class lets a view be refused before anything is built, for asking a frontend
  to attach something it does not, for not being the type that placement
  demands, and for being declared in the wrong layer; a view answering from a
  property is checked once it exists. `NamedComponent` and
  `AttachableComponent` are the protocols the built components are held to,
  without a base class to inherit. `NamedComponent` is `name` alone, and every
  component clears it: a session may declare two components of one class, and
  the declared name is what tells them apart, so one that drops the name it was
  constructed with is refused. `AttachableComponent` adds `placement` to it, and
  is what `AppContainer.views` is typed by.

  ```python
  from redsun.experimental import AttachableComponent, NamedComponent
  ```

  Once the wiring is applied, two relations are reported without stopping the
  build. A component that shares nothing, asks for nothing and is wired to
  nothing is named, which is what a wiring rule with a typo in a component name
  looks like: the rule naming a component that does not exist already fails, and
  the component no rule names did not. A `provides` return type no component
  asks for is named with its method, which is what a consumer removed while the
  producer stayed looks like. Both are legal, so both are warnings: a session
  under construction has components nothing reaches yet, and a bundle may ship
  one a particular session does not need. Being injected by another component
  counts as being used, as does answering a `Requires`, `RequiresOne` or
  `RequiresMaybe` question.

  A plugin bundle may ship a dishka `Provider` of its own, declared at dishka's
  `Scope.APP`; an application has one stage, so no narrower scope is entered and
  a provider written for another dishka application drops in unchanged.

  `VirtualContainer` owns the application's lifetime. `on_release` registers a
  finalizer and `release` undoes everything in reverse: connections first, then
  each component's `shutdown` in reverse construction order, then the dependency
  graph, then devices. A component takes part by declaring `shutdown`, sync or
  async, and nothing else.

  See [The experimental container](../explanation/experimental-container.md) for
  the architecture, what it lifts off component authors, and what it gives up.

## [0.12.0] - 29-08-2026

### Added

- **`WrapsBuild`** (`redsun.containers._hooks`) and **`QtWrapsBuild`**
  (`redsun.qt`) - the `during_build` hook point, which surrounds the whole
  build. `during_build` returns a context manager entered before the first
  component is built and left once the window is shown; what it yields is
  called with the name of each build step as it starts.

  ```python
  class Splash:
      @contextmanager
      def during_build(self, app: QApplication) -> Generator[Callable[[str], None]]:
          screen = QSplashScreen(QPixmap("logo.png"))
          screen.show()
          try:
              yield screen.showMessage
          finally:
              screen.close()
  ```

- **`AppContainer.BUILD_STEPS`** - the step names `build` announces, in order,
  so a progress display sizes itself from the framework rather than from a
  count of its own.

  The steps reported are `virtual container`, `devices`, `presenters`, `views`,
  `providers`, `wiring` and `injection`. The span opens on
  `QtAppContainer.run`, not on `build`, and closes when the build raises.
  `run` processes events once after showing the main window and before leaving
  the span, so the window has painted by the time a splash is dismissed. A
  provider serving `configure_main_view` as well holds the window and can hand
  over with `QSplashScreen.finish` instead of `close`.

- **`set_level`** (`redsun.log`) - sets the level of the `redsun` logger. Takes
  a `logging` constant or a level name, as `logging.Logger.setLevel` does; a
  name is matched without regard to case.

- **`add_handler`** and **`remove_handler`** (`redsun.log`) - install and
  uninstall a destination for the `redsun` logger's records. A handler carrying
  no formatter of its own is given the one every other destination writes
  through.

  ```python
  from redsun.log import add_handler, remove_handler

  handler = MyHandler()
  add_handler(handler)
  ...
  remove_handler(handler)
  ```

- **`log_level`** - a keyword on `AppContainer.__init__` and on
  `AppContainer.from_config`, giving the level the session runs its logger at.
  The logger is left as it is when it is not given.

  ```python
  container = AppContainer.from_config("session.yaml", log_level=logging.DEBUG)
  ```

- `config` accepts several YAML files, layered in the order given, and a
  container class reads what its bases named before its own. A file common to
  several sessions sits under the one particular to each.

  ```python
  class InstrumentApp(QtAppContainer, config="common.yaml"):
      ui = declare_view(MyView, from_config="ui")


  class Simulation(InstrumentApp, config="simulation.yaml"): ...


  class Instrument(InstrumentApp, config="instrument.yaml"): ...
  ```

- `AppContainer._config_paths` reports those files in the order they layer, and
  `AppContainer._component_fields` records the `declare_*` fields a container
  and its bases declared.

### Changed

- The `redsun` logger starts at `INFO` rather than `DEBUG`, and is configured
  with `logging` calls rather than a `dictConfig` mapping. `redsun.log.config`,
  `redsun.log.InfoFilter` and `redsun.log.DebugFilter` are gone: the two stream
  handlers they split records between wrote to one `sys.stdout` through one
  formatter, which is now a single handler installed with `add_handler`.
- `AppContainer` declares no hook points. Every point belongs to a toolkit, so
  `QtAppContainer` declares all four - `create_application`,
  `configure_application`, `during_build` and `configure_main_view` - and a
  `hooks` section naming a point on a plain `AppContainer` is refused.
- A hook never changes what the container builds or the order it builds it in.

  See [Toolkit hook
  points](../explanation/decisions/0010-toolkit-hook-points.md).

- A `declare_*` field with `from_config` is resolved against the configuration
  of each container class that inherits it, rather than only the one that
  declared it. A base class can therefore carry the declarations two sessions
  share while each subclass reads its own files.
- A subclass naming `config` adds to the files its bases named instead of
  replacing them.
- Configuration files merge as mappings, recursively: a key present in two
  files is taken from the later one unless both values are mappings, which
  merge in turn. Lists and scalars are replaced, not combined.
- The `devices`, `presenters` and `views` sections merge by component name, but
  a component named in a later file is taken from that file whole. A component
  entry is a constructor's keyword arguments, so one file owns all of them.
- The keys `AppConfig` requires are checked against the merged configuration
  rather than against each file, so a file layered under another may carry a
  fragment.
- `schema_version` and `frontend` must agree across layered files. They name
  what kind of session this is rather than what it contains, so a later file
  giving a different value raises `ValueError` instead of overriding. Every
  other key, `session` included, is taken from the later file.
- A container reading more than one configuration file logs them at debug
  level, in the order they layer, and logs each component an upper file takes
  from a lower one.
- A container inheriting from more than one base reads the files every base
  named, rather than only those of the first in the method resolution order. A
  file reached twice through the hierarchy is read once.
- A configuration section written with nothing under it - `presenters:` and no
  entries - is read as an empty section rather than raising `AttributeError`.
- Declaring a `from_config` field on a container class with no `config` file no
  longer raises at class creation; the `TypeError` is raised when such a
  container is constructed, and names every field that asked for a section.
  A base class exists to be subclassed, and the subclass is where `config` is
  named.

  See [Inherited and layered component
  configuration](../explanation/decisions/0009-inherited-component-configuration.md).

- A required plan parameter annotated with a sequence of a non-device type -
  `Sequence[int]`, `list[str]` - no longer raises `UnresolvableAnnotationError`.
  The Qt view builds a list editor for it; the check that runs before the view
  exists did not know that, and skipped the plan.

- Bump `ophyd-async` to 0.21.2.
- Bump `acquire-zarr` to 0.9.0.

### Fixed

- A plan with a required `bool` parameter no longer crashes the Qt parameter
  form with `TypeError: setChecked(...) argument 1 has unexpected type
  'NoneType'`. A parameter with no default is now given magicgui's `Undefined`
  rather than `None`.

### Removed

- **`AppContainer.phases`**, **`AppContainer.register_phase`** and
  **`AppContainer.unregister_phase`** - the build sequence is a straight-line
  body again and cannot be added to.
- **`AppContainer.sig_phase_complete`** - a `during_build` provider is given a
  reporter instead. It was the only psygnal `Signal` on `AppContainer`, so
  `__weakref__` leaves its `__slots__`.
- **`ConfiguresBuild`**, **`ConfiguresSession`**, **`AppConfiguresBuild`** and
  **`AppConfiguresSession`** (`redsun.containers`) - the `configure_build` and
  `configure_session` hook points are gone with the registry and the
  after-the-build moment.

## [0.11.2] - 28-08-2026

### Added

- **Container hooks** - an object a session installs on its application
  container to adjust the application as a whole. Each hook point is named by
  the method it calls, and takes one provider.

  Providers are named in a configuration file by dotted path, under the point
  they serve, with their constructor arguments under `kwargs`:

  ```yaml
  hooks:
    configure_build:
      provider: "mypkg.hooks:Calibration"
      kwargs:
        passes: 3
  ```

  or declared on a container class with `declare_hook`:

  ```python
  class MyApp(QtAppContainer):
      configure_build = declare_hook(Calibration, passes=3)
  ```

  A subclass inherits the points its bases declare. One provider serves several
  points when it is the same object at each: the same instance in Python, a
  YAML anchor and its alias in a file.

  ```yaml
  hooks:
    configure_application: &theme
      provider: "mypkg.hooks:DarkTheme"
    configure_main_view: *theme
  ```

  `HookError` is raised for an entry that does not resolve, a key that is not a
  hook point the container calls, a provider that does not implement the
  protocol its point calls, a point named both on the container class and in
  the configuration, and two separate entries naming one provider with the same
  keys. The hook points below are listed in the order a session reaches them.

  See [Container hooks and the build phase
  registry](../explanation/decisions/0008-container-hooks-and-the-phase-registry.md).

- **`declare_hook`** (`redsun.containers`) - declares a hook provider on a
  container class, at the point the attribute names. Takes a class with
  keyword arguments, or a provider already built.

  ```python
  class MyApp(QtAppContainer):
      configure_application = declare_hook(DarkTheme, palette="nord")
  ```

- **`QtCreatesApplication`** (`redsun.qt`) - supplies the `QApplication` the
  session runs on. Called only when no `QApplication` is running yet.

  ```python
  class BrandedApplication:
      def create_application(self, argv: list[str]) -> QApplication:
          return QApplication(argv)
  ```

- **`QtConfiguresApplication`** (`redsun.qt`) - adjusts the `QApplication`
  before the build constructs any view.

  ```python
  class DarkTheme:
      def configure_application(self, app: QApplication) -> None:
          app.setStyleSheet(...)
  ```

- **`ConfiguresBuild`** (`redsun.containers`) - adjusts the build sequence
  before any phase of it runs. The only point at which `register_phase` and
  `unregister_phase` are legal.

  ```python
  class Calibration:
      def configure_build(self, container: AppContainer) -> None:
          container.register_phase("calibrate", self._run, after="injection")
  ```

- **`ConfiguresSession`** (`redsun.containers`) - runs after the last build
  phase, with `is_built` already set, so `devices`, `presenters` and `views`
  are readable.

  ```python
  class Autostart:
      def configure_session(self, container: AppContainer) -> None:
          self._log(container.devices, container.presenters, container.views)
  ```

- **`QtConfiguresMainView`** (`redsun.qt`) - adjusts the main window after it
  is built and before it is shown. Bound to `QMainWindow`, not to the window
  class the container builds.

  ```python
  class DarkTheme:
      def configure_main_view(self, view: QMainWindow) -> None:
          view.setWindowIcon(...)
  ```

- **`HasShutdown`** (`redsun.virtual`) - now called on hooks as well as
  presenters. Hooks are torn down in reverse order, after the presenters, once
  each however many points a provider serves; a failing teardown is logged and
  does not block the rest. The container then restores the phase sequence it
  captured before the hooks ran.

  ```python
  class DarkTheme:
      def shutdown(self) -> None:
          self._app.setStyleSheet(self._previous)
  ```

- The three toolkit hook points are one generic protocol each
  (`CreatesApplication`, `ConfiguresApplication`, `ConfiguresMainView`),
  aliased per toolkit.

- **`AppConfiguresBuild`** and **`AppConfiguresSession`** (`redsun.containers`)
  - `ConfiguresBuild` and `ConfiguresSession` bound to `AppContainer`. Both
  protocols are parameterised on the container they act against, so a container
  implementation supplies its own aliases.

- `AppContainer.phases`, `AppContainer.register_phase(name, phase, after=...)`
  and `AppContainer.unregister_phase(name)` - the build sequence as a registry
  a caller can add to. `after` is required; `unregister_phase` refuses the
  built-in phases. Both are legal only before `build`.

  ```python
  app = MyApp()
  app.register_phase("calibrate", calibrate, after="injection")
  app.build()
  ```

- `AppContainer.sig_phase_complete`, emitted with the name of each build phase
  as it finishes.

  ```python
  class Splash:
      def configure_build(self, container: AppContainer) -> None:
          container.sig_phase_complete.connect(self._show)

      def _show(self, phase: str) -> None: ...
  ```

- `__weakref__` to `AppContainer.__slots__`, required by any `__slots__` class
  owning a psygnal `Signal`.

- `QtAppContainer._ensure_main_view`, so the main window is built and
  configured once whether reached through `run` or directly.

## [0.11.1] - 25-08-2026

### Changed

- A presenter or view that fails its protocol check at build time now reports
  every member it is missing, instead of naming the members a correct component
  would have. `TypeError` is still raised for exactly the same components.
- A plugin that cannot be loaded into a manifest group now reports what that
  group requires, instead of "does not implement any known protocol".
- `create_plan_spec` resolves each annotation on its own instead of resolving
  the whole signature at once. An annotation naming something unavailable at
  runtime, such as a type imported only under `TYPE_CHECKING`, now raises
  `UnresolvableAnnotationError` naming the plan and the parameter, where it
  previously raised `NameError` from `typing`. Such a plan is still rejected:
  callers that already handle `UnresolvableAnnotationError` can skip it
  instead of failing the surrounding build.

## [0.11.0] 01-08-2026

### Added

- `slot` (`redsun.virtual`) - marks a method as connectable, making its name and
  signature part of a component's public surface. Only a marked method can be
  connected to a signal. `@slot(name=...)` sets the port name used in
  configuration; `@slot(thread=...)` overrides the thread affinity declared by
  the class.
- `AppContainer.wire()` - override to declare the connections of an
  application. It runs after `register_providers` and before
  `inject_dependencies`; component attributes resolve to their built instances
  while it runs, so a connection reads as
  `self.connect(self.det_ctrl.sig_new_data, self.img_widget.update_layers)`.
- `AppContainer.connect()` and `VirtualContainer.connect()` - connect a signal to
  a slot, applying the thread affinity of the slot or its class and recording the
  link. A slot that is not marked, or whose signature psygnal rejects, raises
  `WiringError` naming both ports.
- `VirtualContainer.connections` and `VirtualContainer.disconnect_all()` - the
  recorded wiring graph and its teardown. `AppContainer.shutdown()` now
  disconnects everything it connected.
- `ports()` and `Ports` (`redsun.virtual`) - the signals and slots a component
  exposes, by port name. `SignalGroup` members appear under the member name.
- A `wiring` section in the configuration file, listing `from` / `to` port
  paths (`component.port`) for a session that has no container class to
  override. Applied after `wire()`, through the same `connect`.
- `VirtualContainer.connect_paths()` - the string form of `connect`, used by
  that section. A malformed path, an unbuilt component, or an unknown port
  raises `WiringError` listing what does exist.
- `Connection` and `WiringError` (`redsun.virtual`).
- `VirtualContainer.provide()`, `require()` and `try_require()` - share an
  object under a typed key instead of a dynamic attribute. `require` raises
  `KeyError` when nothing bound the key; `try_require` returns `None`, which is
  how an optional collaborator is expressed.
- `ProviderKey` (`redsun.virtual`) - the type of such a key, a
  `dependency_injector.providers.Dependency[T]`. `instance_of=` is enforced by
  `provide`, so a wrong value is blamed where it is supplied.
- `PATH_PROVIDER` (`redsun.storage`) - the key for the session path provider
  owned by `StoragePresenter`.
- `VirtualContainer.subscribe()` and `VirtualContainer.subscriptions` - observe
  an ophyd-async device signal from a marked slot. The reading is marshalled
  through psygnal, so `thread` behaves as it does for `connect`, and the
  subscription is released by `disconnect_all()`. Previously a component had to
  call `subscribe_reading` itself, from inside a coroutine, with no way to set a
  thread affinity and nothing tracking the release.
- `Subscription` (`redsun.virtual`) - the record of one, rendered as
  `source ~> consumer.port`.
- `SlotThread` (`redsun.virtual`) - the type of a thread affinity, so a
  component can annotate its `__redsun_slot_thread__` declaration.
- `VirtualContainer.unconnected` and `Unconnected` (`redsun.virtual`) - the
  ports of the built components that no connection or subscription reaches, as
  `component.port` paths. A misspelled port fails at build; a connection that
  was never written fails nowhere, and this is what finds it. Falsy when
  everything is reached, so a script can assert on it.
- `StorageView` (`redsun.view.qt.builtins`) - a Qt widget showing and
  editing the base directory of the provider bound to `PATH_PROVIDER`. Without
  a `StoragePresenter` in the application it degrades to a read-only
  placeholder. Available from a configuration file as `plugin_name: redsun`,
  `plugin_id: storage` under `views`, which the shipped manifest now declares.

### Changed

- `QtView` declares `__redsun_slot_thread__: ClassVar[SlotThread] = "main"`, so every slot on a Qt
  view is delivered on the main thread unless the slot or the connection says
  otherwise. Connections that passed `thread="main"` explicitly still work and
  are now redundant.

- `declare_device()`, `declare_presenter()` and `declare_view()` return the
  class they are given instead of `Any`, so a component attribute is typed as
  its component. A connection in `wire()` that names a port the class does not
  have is now a type error, where before it was only a build failure. No
  container needs changing: existing declarations become checked as they are.
- `StoragePresenter` binds its provider with
  `container.provide(PATH_PROVIDER, ...)`. **Breaking:** the dynamic attribute
  it used to set is gone; read the provider with
  `container.require(PATH_PROVIDER)` instead of `container.path_provider()`.
- `StoragePresenter` exposes `set_plan` and `reset_plan` as slots instead of
  discovering `sig_pre_launch_notify` and `sig_plan_done` by name in
  `inject_dependencies`. **Breaking:** an application that relied on that
  discovery must now connect them, in `wire()` or in the `wiring:` section:

  ```python
  self.connect(self.acquisition.sig_pre_launch_notify, self.storage.set_plan)
  self.connect(self.acquisition.sig_plan_done, self.storage.reset_plan)
  ```

  Which signals announce a plan is the application's knowledge; the presenter
  no longer guesses it from a name, and a misspelled one now fails instead of
  silently connecting nothing.

  `find_signals` and hand-written `inject_dependencies` are otherwise
  unaffected.
- `redsun.aio.set_async_backend()` - installs `CulsansAsyncioBackend` as psygnal's
  active async backend, so coroutines connected to a signal are dispatched onto the
  shared event loop from any thread. Idempotent; raises if a different backend is
  already active. Tear it down with psygnal's `clear_async_backend()`.
  `QtAppContainer` calls it in `build()` and clears it in `shutdown()` (ADR 0005).
- `CulsansAsyncioBackend` and `AwaitableEvent` (`redsun.aio`) - the backend itself and
  the resettable, awaitable event it reports `running` through. Exceptions raised by a
  dispatched slot are logged on the `redsun` logger instead of being discarded.

### Changed (breaking)

- `get_shared_loop()` is no longer re-exported from `redsun.engine`; import it from
  `redsun.aio`, where it is defined. It is the only piece of the async runtime
  intended for use outside the application container, alongside `run_coro()`.

## [0.10.0] 25-07-2026

### Added

- `get_shared_loop()` (`redsun.engine`) - returns the single `asyncio` event loop created
  at module import time.
- `AppContainer.connect_devices(mock=False)` - connects all registered ophyd-async devices
  via their async connect lifecycle. Call after `build()`. Pass `mock=True` to skip hardware
  communication in tests.
- `FrameSink`, `StoreStateError`, and the process-wide storage registry
  (`register_storage`, `get_storage`, `reset_group`, `clear_registry`).
- culsans (>=0.11.0) as a runtime dependency.
- `redsun.presenter.builtins` - built-in, reusable presenter components.
  First entry: `StoragePresenter` (ported from redsun-mimir's
  `FileStoragePresenter`), which owns the `SessionPathProvider`, exposes it
  on the virtual container as the `path_provider` DI provider, and wires
  plan names from `sig_pre_launch_notify`/`sig_plan_done`.
- `redsun.plugins` entry point: redsun ships its own plugin manifest
  (`plugins.yaml`), so built-in components resolve from configuration files
  through the same discovery path as external plugins
  (`plugin_name: redsun`, `plugin_id: storage`).
- `BaseStorage.path_provider` read-only property.
- `find_signals` accepts an optional `owner` keyword to scope the lookup to
  one component's signal cache (ADR 0004).
- `SinkFactory`, `StorageIO`, `OpenStore`, and `PathSignals` are exported from
  `redsun.storage` - the backend protocols are part of the public contract.
- `benchmarks/` - acquire-zarr dual-load benchmark (live view via
  `bps.monitor` + disk storage, two detectors, inline processing callback).
  Shipped in the sdist only, never in wheels, not collected by pytest.
- Tutorial: [writing a custom storage backend](../tutorials/custom-storage-backend.md)
  (`StorageIO`/`OpenStore` implementation driven through `BaseStorage`).

### Changed (breaking)

- `redsun.storage` rewritten per ADR 0002: `BaseStorage.sink()` returns a
  `FrameSink` (culsans-backed) usable from async device logics and sync
  document callbacks; `open()`/`close()` are explicit and idempotent.
- Removed `StorageStateMachine`, `StorageState`, `InvalidStoreState`, and the
  `FrameSender` async-generator API. `StoreStateError` replaces
  `InvalidStoreState`.
- Removed `redsun.device.DeviceMap` - ophyd-async now ships `DeviceMap` as a
  built-in; import it from `ophyd_async.core` instead (downstream consumers
  such as redsun-mimir should migrate on their next refactor).
- Signal naming convention: `sig_snake_case` replaces `sigCamelCase`
  (ADR 0004). `StoragePresenter` wires `sig_pre_launch_notify` /
  `sig_plan_done`; `DescriptorTreeView.sig_property_changed` renamed.
- Presenter/view protocols reworked for sound structural subtyping (ADR
  0003): `PPresenter.name`/`devices` and `PView.name` are read-only property
  members; the `Presenter`/`View` ABCs no longer inherit the protocols;
  validation is a dual gate - constructor positional shape
  (`(name, devices)` / `(name,)`) checked via `inspect` at
  declaration/discovery, protocol compliance validated on built instances
  (raising `TypeError`) - replacing the class-level attribute screen;
  `AppContainer.presenters` and `.views` are typed `dict[str, PPresenter]`
  / `dict[str, PView]`.

### Changed

- **Custom device layer removed**, `redsun.device` now re-exports ophyd-async primitives
  directly. Removed: `PDevice`, `HasChildren`, `AttrR`, `AttrRW`, `AttrW`, `AttrT`,
  `SoftAttrR`, `SoftAttrRW`, `SoftAttrT`, `AcquisitionController`, `DataWriter`,
  `ControllableDataWriter`, `TriggerType`, `PrepareInfo`. Use their ophyd-async equivalents
  (`Device`, `StandardReadable`, `SignalR/RW/W/X`, `soft_signal_rw`,
  `soft_signal_r_and_setter`, `DetectorController`, `DetectorWriter`, `TriggerInfo`,
  `DetectorTrigger`).
- `device()`, `presenter()`, `view()` field specifiers renamed to `declare_device()`,
  `declare_presenter()`, `declare_view()` for clarity. Update all container subclasses and
  imports accordingly.
- `AppContainerMeta` metaclass replaced with `__init_subclass__` for container subclass
  registration.
- Dropped `beartype` as a runtime dependency.
- Updated CI tag pattern to support release candidates (e.g. `v0.10.0rc0`).
- Re-enabled CI after the test-suite rewrite: the cross-platform test matrix
  and Codecov upload run again, and docs deployment / package build depend on
  green tests once more. CI mypy now uses the config-driven invocation (tests
  and benchmarks in scope) with `QT_API` pinning the Qt binding per matrix
  leg, and ruff checks the whole repository instead of `src/redsun` only.

### Removed
- Removed `attrs` from dev dependencies - drop support for it in favor of `ophyd-async`.
- Removed unused utilities: `redsun.utils.resolve_sync_or_async` and
  `redsun.utils.descriptors.make_key` / `make_descriptor` / `make_reading` - descriptors and readings come from ophyd-async signal backends; the
  `parse_key` / `parse_map_key` helpers remain.

## [0.9.1] - 06-03-2026

- Moved documentation dependencies to separate group
- Added support for `boolean` dtype descriptor
- Updated lockfile

## [0.9.0] - 27-02-2026

### Added
- Migrated code from `redsun-mimir` to here
  -  In particular the whole plan specification and action system
  -  Some things still require additional tests, although have been empirically tested in `redsun-mimir`
- `DeviceSequenceEdit`: new `ValueWidget` subclass rendering `Sequence[PDevice]` and `Set[PDevice]`
  parameters as a checkbox list with a live selection count label.
- `PlanWidget.device_widgets`: exposes device parameter widgets for external validation.
- `PlanWidget.params_widget`: single `QWidget` wrapping the Devices and Parameters group boxes;
  disabled atomically during plan execution so all inputs lock without affecting run/stop/pause buttons.
- `Set[PDevice]` / `AbstractSet[PDevice]` annotation support in plan spec: `isdeviceset` predicate
  and `_handle_device_set` handler; `resolve_arguments` coerces to `set()` for set-typed params.
- `HasWriter` protocol expressing the ability of a device to encapsulate a writer.
- `SessionPathProvider` with automatic run-number increment, replacing `AutoIncrementFileProvider`.
- Metadata registry on `Writer`; metadata collected at `prepare` time is written immediately after
  stream open.
- `clear_sources` mechanism for presenters to explicitly clear writer sources after a plan finishes.
- `group` parameter on path providers for sub-group addressing within a Zarr store.

### Changed
- Storage layer migrated to per-device `Writer` instances identified by URI (singleton via `get()`).
- Device preparation migrated from `StorageInfo`/`StorageConfig` dict-based API to `PrepareInfo`.
- `make_writer` signature updated to `(uri, mimetype)`.
- Shareable plan-spec and widget infrastructure migrated from redsun-mimir into the SDK.
- `create_plan_widget` now splits device and scalar parameters into separate "Devices" and
  "Parameters" group boxes.
- Widget factory predicates now match on annotation shape rather than `choices is not None`;
  empty-choices case produces a valid empty widget instead of raising `RuntimeError`.
- `_try_factory_entry` now only swallows predicate errors; factory crashes propagate immediately.
- `is_device_set` removed from `ParamDescription`; set coercion derived from annotation directly
  via `isdeviceset(p.annotation)`, symmetric with how `isdevicesequence` was already handled.

## [0.8.2] - 23-02-2026

### Changed

- Drop the `Static` and `UUID` filename providers in favor of `AutoIncrement` as default
  -  Will be reintroduced at a later date when storage API is stabilized

### Fixed

- Fixed broken links in changelog
- Store the suffix of a `FilenameProvider` or it gets lost
- Convert URI to standard path for `acquire-zarr` backend

### Added

- Added some helper utilities for making descriptor/reading keys following canonical convention

## [0.8.0] - 22-02-2026

### Changed

- Migrated sunflare codebase to redsun. Sunflare will be archived.

## [0.7.2] - 22-02-2026

### Changed

- Merged SDK (formerly sunflare) into redsun
- Migrated the HasStorage protocol to toolkit

### Fixed

- Fixed path lookup for storage

## [0.7.0] - 21-02-2026

### Added

- Added initial support for opt-in storage capacities for devices via descriptor protocol
- Currently supporting only Zarr V3 format via `acquire-zarr`

## [0.6.1] - 20-02-2026

### Fixed

- Allow multiple widgets to be stacked in the center via `QTabWidget` for `QtAppContainer`
- Fix the attribute look-up in loop construction to get the `view_position` attribute of `PView`

## [0.6.0] - 20-02-2026

### Added

- Added `device()`, `presenter()`, `view()` typed field specifiers for declarative component registration

### Changed

- `IsProvider.register_providers()` now runs over both presenters and views
- `IsInjectable.inject_dependencies()` now runs over both presenters and views
- Refactored build loop in component construction, provider registration and dependency injection
- `_ComponentBase`: alias slot removed; name fully resolved at metaclass time
- `_PresenterComponent.build()`: removed unused container: VirtualContainer parameter
- All `_*Component.build()` methods use self.name directly
- Changed plugin manifest format: from `{ class: "module:Type" }` to flat `"module:Type"` string
- Updated documentation

### Removed

- Removed `component()` catch-all field declarator in favor of layer-specific functions

## [0.5.6] - 18-02-2026

### Fixed

- `AppContainer.build()` now calls
  `connect_to_virtual()` on all `VirtualAware`
  **view** components after all components are fully constructed, symmetrically
  with the existing presenter loop. Previously, views were connected only via a
  `QtMainView` delegator called from `QtAppContainer.run()`, meaning the wiring
  was Qt-specific and bypassed the base build phase entirely.
- Removed the now-redundant `connect_to_virtual()` delegator from `QtMainView`
  and the explicit call to it in `QtAppContainer.run()`.
- Fixed a spurious warning when a `from_config` key exists in the YAML but has
  no kwargs (bare key with null value, e.g. `camera2:` with nothing after it).
  Previously `dict.get()` returned `None` for both a missing key and a null
  value, making them indistinguishable. A sentinel is now used so only a
  genuinely absent key triggers the warning; a present-but-empty section is
  silently normalised to `{}`.

### Added

- `redsun.qt` public namespace exposing `QtAppContainer` for use in explicit,
  developer-written application configurations:
  ```python
  from redsun.qt import QtAppContainer
  ```
- Clarified documentation

## [0.5.4] - 18-02-2026

### Fixed

- Relaxed the `component()` overloads: all three (`layer="device"`, `layer="presenter"`,
  `layer="view"`) now accept `type` instead of `type[Device]`, `type[Presenter]`,
  `type[View]`. This fixes mypy errors for classes built from protocol mixins that do
  not inherit from the sunflare base classes directly.

## [0.5.3] - 18-02-2026

!!! warning

    This release was yanked from PyPI due to a broken distribution

### Added

- `AppContainer` and `component` are now importable directly from the top-level
  `redsun` package:
  ```python
  from redsun import AppContainer, component
  ```

### Changed

- `component()` now takes the component class as its first positional argument:
  ```python
  # Before
  motor: MyMotor = component(layer="device", axis=["X"])
  # After
  motor = component(MyMotor, layer="device", axis=["X"])
  ```
- `RedSunConfig` removed from the public API; it is an internal `TypedDict` used
  only for YAML configuration validation.

## [0.5.0] - 17-02-2026

### Changed

- Fully refactor the package to go towards a containerization approach
  - Declare applications as containers, list relevant components as fields of a class
  - Provide support also for building from a configuration file as before
- Upgrade to `sunflare>=0.9.0`
- Move the `FrontendTypes` and `ViewPositionTypes` from `sunflare` to `redsun`
  - They're part of the overall configuration and should not concern the core package
- Revamped documentation with more comprehensive information

## [0.4.0] - 15-12-2025

### Changed

- Apply a more strict check on imported plugins
- Add support for 3.13 (simply declared on PyPI and tested via CI)
- Upgrade to `sunflare>=0.7.0`

## [0.3.0] - 04-07-2025

### Changed

- Upgraded to `sunflare>=0.6.1`
- Switch to `uv`
- Drop support for Python 3.9

## [0.2.0] - 03-03-2025

### Changed

- Reworked the plugin system
  - The approach now loosely follows the [`napari` manifest](https://napari.org/stable/plugins/technical_references/manifest.html), where plugins are to be published via a `yaml` configuration file in the root folder of the plugin package, specifiying where the classes have to be imported.
  - The manifest is taken as the actual entry point of a plugin, which will be used to redirect to the actual imports which is executed via the standard library `importlib`.
- Added additional coverage for the ``factory`` module.
- Bumped sunflare version to ``sunflare>=0.5.0``, which implements the above changes at toolkit level

## [0.1.0] - 22-02-2025

### Added

- Initial release on PyPI

[0.12.0]: https://github.com/redsun-acquisition/redsun/compare/v0.11.2...v0.12.0
[0.11.2]: https://github.com/redsun-acquisition/redsun/compare/v0.11.1...v0.11.2
[0.11.1]: https://github.com/redsun-acquisition/redsun/compare/v0.11.0...v0.11.1
[0.11.0]: https://github.com/redsun-acquisition/redsun/compare/v0.10.0...v0.11.0
[0.10.0]: https://github.com/redsun-acquisition/redsun/compare/v0.9.1...v0.10.0
[0.9.1]: https://github.com/redsun-acquisition/redsun/compare/v0.9.0...v0.9.1
[0.9.0]: https://github.com/redsun-acquisition/redsun/compare/v0.8.2...v0.9.0
[0.8.2]: https://github.com/redsun-acquisition/redsun/compare/v0.8.0...v0.8.2
[0.8.0]: https://github.com/redsun-acquisition/redsun/compare/v0.7.2...v0.8.0
[0.7.2]: https://github.com/redsun-acquisition/redsun/compare/v0.7.0...v0.7.2
[0.7.0]: https://github.com/redsun-acquisition/redsun/compare/v0.6.1...v0.7.0
[0.6.1]: https://github.com/redsun-acquisition/redsun/compare/v0.6.0...v0.6.1
[0.6.0]: https://github.com/redsun-acquisition/redsun/compare/v0.5.6...v0.6.0
[0.5.6]: https://github.com/redsun-acquisition/redsun/compare/v0.5.5...v0.5.6
[0.5.5]: https://github.com/redsun-acquisition/redsun/compare/v0.5.4...v0.5.5
[0.5.4]: https://github.com/redsun-acquisition/redsun/compare/v0.5.3...v0.5.4
[0.5.3]: https://github.com/redsun-acquisition/redsun/compare/v0.5.2...v0.5.3
[0.5.0]: https://github.com/redsun-acquisition/redsun/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/redsun-acquisition/redsun/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/redsun-acquisition/redsun/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/redsun-acquisition/redsun/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/redsun-acquisition/redsun/compare/v0.1.0
