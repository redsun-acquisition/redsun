# Experimental changelog

This page lists the unreleased changes to `redsun.experimental`, and the
changes to the rest of the package made alongside it. Released versions are
listed in the [changelog](changelog.md).

## [Experimental]

### Added

- `redsun.experimental` - a second container layer, behind the `experimental`
  extra, which carries `in-n-out`. **Not covered by any stability guarantee**:
  names and behaviour may change or be withdrawn in any release.
  `redsun.containers` remains the supported layer. See
  [The experimental container](../explanation/experimental-container.md) for the
  architecture, what it lifts off component authors, and what it gives up.

  Components are declared as annotations rather than `declare_*` calls, each
  naming the layer it belongs to, and a component's collaborators are
  constructor parameters resolved by type:

  ```python
  class MyApp(QtSession):
      config = "session.yaml"

      stage: AsDevice[MyStage]
      motor_ctrl: AsPresenter[MotorPresenter]
      motor_widget: Annotated[AsView[MotorView], Declare(step_size=5.0)]
  ```

- `AsDevice`, `AsPresenter` and `AsView` wrap the component's own type without
  replacing it, so the attribute stays typed as what it holds. One of them marks
  an annotation as a component, so a container class may hold ordinary
  attributes beside its components. A device must subclass
  `ophyd_async.core.Device`, and a class that subclasses it is refused in either
  other layer. A presenter or view must take `name` as its first parameter,
  positionally or as a keyword, so a pydantic model whose fields are all
  keyword-only can be a presenter; a name that could only arrive inside `*args`
  or `**kwargs` is refused. A component appearing only in the session file takes
  its layer from the section it sits under, and is checked the same way. The
  three are also reachable as `redsun.experimental.session.components`. A built
  component is set on the session under its name, so a name the session never
  declared raises `AttributeError` and a type checker refuses it, and a
  component that failed to build raises rather than reading as `None`.

- `Declare`, `FromConfig` and `Alias` - inline keyword arguments, the
  configuration key an entry is read from, and the name a component is declared
  under. The attribute name is both by default. A component may not be named
  after something the container already answers, such as `devices` or `run`.

- `provides` marks a method whose return value other components may ask for,
  replacing `register_providers`. A parameter annotated `X | None` is `None`
  when nothing supplies `X`, replacing `try_require`, and a parameter carrying a
  default keeps it when the session supplies neither a value nor a configuration
  entry. `IsProvider`, `IsInjectable`, `ProviderKey` and the `provide`/`require`
  pair have no equivalent, and `VirtualContainer` is not among the types a
  component may ask for.

- `Session.providers` - a list of ordinary classes, one of which a
  `providers:` manifest entry resolves to. A provider's constructor is filled
  from the session, and every method it marks with `provides` registers a value
  under that method's return type:

  ```python
  class MyServices:
      def __init__(self, config: SessionConfig) -> None:
          self._config = config

      @provides
      def calibration(self) -> Calibration:
          return Calibration(...)
  ```

  A provider may be a plain class, a dataclass (frozen and slotted included) or
  a pydantic model. It is given no name, so a parameter called `name` is one the
  session must answer like any other.

- Components are built in layer order, and within a layer in the order they are
  built from one another, so a component may be written above the one it depends
  on. Two components of one layer built from each other raise `TypeError`. A
  component may depend on its own layer or an earlier one and never on a later
  one, so a presenter naming a view, or a type only a view shares, is refused
  before anything is constructed, naming both components and both layers. Two
  views sharing a value needs no publish-then-resolve pass: one shares it with
  `provides`, the other asks for it in `__init__`. `Requires[P]` is exempt.

- `Session.build` logs a component that fails to build and carries on, in
  every layer. The component is absent from `presenters` or `views`, and so is
  one built from it. The closing line counts what was built against what was
  declared and is logged at `WARNING` when anything failed:

  ```
  Container built: 1/2 devices, 1/3 presenters, 0/0 views
  Not built: bad_stage (device), broken (presenter), dependent (presenter)
  ```

  A component asking for something nothing in the session declares still raises
  `TypeError`.

- `BlueskyCallbackRegistry` - the callback registry as a component sees it, a
  live view rather than a snapshot. A component registers through
  `BlueskyCallbackRegistry.register` while it is built and reads the view once
  the session is built:

  ```python
  class MyPresenter:
      def __init__(self, name: str, /, callbacks: BlueskyCallbackRegistry) -> None:
          self.name = name
          callbacks.register(self, name=name)
  ```

- The callback catalogue - every component that is a `DocumentRouter`, under
  its name and in declaration order, for a component asking for
  `Mapping[str, CallbackType]`. A component asking for it is built after every
  router, so the mapping is complete when it arrives. A router in a later layer
  than the component asking is refused before anything is built, and a router
  that fails to build is absent. `CallbackType` is exported from
  `redsun.experimental`:

  ```python
  class MyPresenter:
      def __init__(self, name: str, /, callbacks: Mapping[str, CallbackType]) -> None:
          self.name = name
          self.callbacks = callbacks
  ```

- `Requires[P]` - the components of the session that satisfy a protocol, spelled
  `Annotated[Mapping[str, P], Every()]`. A live view, holding what the build
  made, so a component that failed is absent from it. A component satisfying *P*
  appears in its own answer.

- `RequiresOne[P]` and `RequiresMaybe[P]` - the same question expecting a single
  answer, and ordinary dependencies rather than live views: the component
  arrives built, and whatever answers is constructed first. Which component
  answers is settled before anything is built, so a session holding none
  (`RequiresOne`) or more than one fails to build, naming the components that
  nearly matched and why. `RequiresMaybe` answers `None` for an empty session
  and for one whose answering component failed to build; an asker of
  `RequiresOne` is skipped instead. Both require *P* to declare at least one
  method.

- `DevicesOf[P]` - the same question asked of the devices, which `Requires[P]`
  never answers over, spelled `Annotated[Mapping[str, P], Devices()]`. It is not
  a live view, so it may be read in `__init__`. Ask for `DeviceMapping` to
  receive every device unfiltered.

- `satisfies` and `Satisfying.rejected` - the membership check and why each near
  miss was left out. Membership is structural rather than `isinstance`: an
  implementation must accept every call the protocol permits, so a renamed
  parameter or an extra required one is not a match, while an extra defaulted
  parameter is. Types are not compared, which a type checker does at the call
  site. *P* must be `runtime_checkable`.

- `SessionNotBuilt` - the `LookupError` a live view of the session raises when a
  component reads it during its own construction.

- `Placement`, `Frontend` and `Frontend.requires` - what a view asks the
  frontend to attach it at, the toolkit a container is built against, and the
  table pairing each placement with the type it demands. A container names its
  toolkit by subclassing, `Session.frontend` being a class attribute;
  `Session` itself names none and accepts any placement.
  The core defines `Placement` and no concrete one:
  `redsun.experimental.session.qt` owns `Dock`, `Central`, `MenuItem` and
  `ToolBarItem` alongside the `Qt` frontend that demands a `QWidget` for a dock
  or the centre and a `QAction` for a menu or toolbar entry, and the `attach`
  that fills a `QMainWindow` from a container's `views`:

  ```python
  class Web(Frontend):
      requires = {Route: Page}
  ```

  `Frontend.check_placement` reads that table, and a frontend whose demand is
  not a subclass relation overrides it. A view is refused before anything is
  built for asking a frontend to attach something it does not, for not being the
  type that placement demands, and for being declared in the wrong layer; one
  answering from a property is checked once it exists.

- `NamedComponent` and `AttachableComponent` - the protocols the built
  components are held to, without a base class to inherit. `NamedComponent` is
  `name` alone, and a component that drops the name it was constructed with is
  refused. `AttachableComponent` adds `placement`, and is what
  `Session.views` is typed by.

- `Serializable` - a component supplying the configuration entry that would
  rebuild it:

  ```python
  class MotorPresenter:
      def __init__(self, name: str, /, step: float = 5.0) -> None:
          self.name = name
          self.step = step

      def serialize(self) -> dict[str, float]:
          return {"step": self.step}
  ```

  `Session.serialize` returns the merged configuration, holding what each
  built component asked for under that component's own name and nowhere else. A
  component that implements none of it keeps the entry the session was built
  from, and so does one that asks for a key its constructor does not accept; the
  session reports that at `WARNING` with the component, the keys and the class.
  The constructor's parameters decide which keys are accepted, not the entry the
  session loaded, so the session writes a parameter that took its default, and a
  constructor taking `**kwargs` accepts every key. One refused key discards the
  whole entry rather than only itself.

  `Session.write` writes that configuration to a path as YAML and returns
  it, one flat file whatever the session was built from, so it opens on its own
  with nothing to assemble first. Keys come out in the order the merged
  configuration holds them, and comments do not survive. A path the session was
  built from raises `ConfigurationInUse`: overwriting one replaces what every
  other session reading it gets.

  Every Qt session registers a `Save configuration as...` action under the
  command id `<name>.save_configuration`, joining the menu
  `redsun.experimental.session.qt.SAVE_MENU`, which a window offers by
  passing that id to `setModelMenuBar`. It asks for a path, says in the dialog
  that comments are not kept, writes nothing when the dialog is cancelled, and
  reports a refused path in a warning box rather than failing silently.

  `Session.has_changes` reports whether any component now asks to be
  written differently than it did at the end of the build. The comparison is
  against what each component serialized once the build finished, not against
  the configuration it was built from. A value changed and changed back reads
  as unchanged, and a component that does not serialize itself never reports a
  change.

- `Settings` - what a session remembers about how one user likes to run it, kept
  as one JSON file per session name under `platformdirs.user_config_dir`:

  ```python
  session.settings.set("ask_on_close", False)
  session.settings.get("ask_on_close", True)
  ```

  `Session.settings` opens it in the `registry` step and registers it, so
  an action asks for it by type. A value is written as it is set. A file that is
  missing, unreadable, or not an object leaves the session on the defaults its
  callers ask for, and says so at `WARNING`.

- `BuildableSession` - the steps a session's build runs, a protocol with one
  public abstract method per step, inherited rather than satisfied:

  ```python
  class MyFrontend(Session):
      def start_runtime(self) -> None: ...
      def present(self) -> None: ...
  ```

  `Session.build` calls the steps in order and does nothing else.
  `start_runtime` puts in place what a component cannot be constructed without,
  and `present` assembles what was built into whatever shows it; a container
  bound to no toolkit answers both with nothing. The other steps are
  `read_configuration`, `build_devices`, `open_registry`, `build_presenters`,
  `build_views`, `seal`, `apply_wiring` and `log_summary`, with `make_store`,
  `open_span`, `on_release` and `shutdown` beside them. A session missing a step
  raises `TypeError` when it is constructed, and a type checker refuses it.

- `DesktopSession` - `BuildableSession` plus `main_window` and `run`, generic
  over the window's type, so `QtSession` inherits
  `DesktopSession[QMainWindow]`. `main_window` is a property, and an implementer
  answers it with a property of its own.

- `Session.on_release` and `Session.shutdown` - a step registers how
  to give something back as it takes it, and `shutdown` runs those in reverse:
  connections first, then each component's own `shutdown` in reverse
  construction order, then the devices. A component takes part by declaring
  `shutdown`, sync or async, and nothing else. A build that raises runs the
  releases its finished steps earned before the exception leaves. `shutdown` may
  be called twice, or on a session that was never built, and runs nothing the
  second time.

- `Session.from_config` - a container for a session described by a file or
  a mapping, for a session with no class of its own. The `frontend:` key picks
  the container to build on, so a session naming `pyqt` comes up on
  `QtSession` without importing it, and one naming a frontend the class it
  was called on is not built against is refused. Calling it on a class keeps
  that class's declarations, its `wire` and its toolkit, and what comes back is
  unbuilt. `Session()` also takes the session directly, overriding the
  `config` class attribute for that instance alone.

- `Session.config` accepts several sources, each a path to a YAML file or a
  mapping, and layers them in the order given:

  ```python
  class MyApp(Session):
      config = ["instrument.yaml", {"name": "morning-run"}]
  ```

  A subclass's sources layer over its bases', in the order the method resolution
  order gives, and the sources passed to the constructor layer over the class's
  rather than replacing them. `from_config` accepts the same. Sources must agree
  on `schema_version` and `frontend`, and `ValueError` names the source that
  disagrees; every other key, `name` included, is taken from the last source
  setting it. A component entry under `devices`, `presenters` or `views` is
  replaced whole rather than merged.

- `Session.name` - what the session is called, readable before `build`.
  `Layer.section` - the configuration section a layer's components are declared
  under, the member's own name pluralised, so `Layer.DEVICE.section` is
  `"devices"`.

- `AsHook`, `Serves`, `QtHook` and a `hooks:` configuration section. A hook is
  an annotation carrying `AsHook`, and the attribute name is the point it
  serves:

  ```python
  class MyApp(QtSession):
      configure_application: Annotated[AsHook[MyTheme], Declare(palette="nord")]
      configure_main_view: AsHook[MyBranding]
  ```

  `Serves` names the points instead, and naming several is how one provider
  instance serves them all. `Declare`, `FromConfig` and `Alias` work as they do
  on a component. `QtHook` names the four points `QtSession` calls:
  `create_application`, which supplies the `QApplication`,
  `configure_application`, `during_build` and `configure_main_view`. `Session.hook_points` is empty, so a hook declared
  on a container bound to no toolkit is refused.

  The `hooks:` section takes the same points as keys, each entry carrying
  `provider` and `kwargs`; a YAML anchor aliased under two keys gives one
  provider serving both. `Session.hooks` is the provider installed at each
  point, built once per build. `HookError` covers a point named on the class and
  in the section, a point claimed twice, a point the container does not call,
  and a provider that does not implement the protocol its point calls.

  A `during_build` hook is told `devices`, `registry`, `presenters`, `views`,
  `seal`, `wiring`, `presentation` and `report`. `read_configuration` and
  `start_runtime` run before the span it opens and are not announced to it.

- An `actions:` section in the configuration of a Qt session, read at build and
  registered on the `Application` the session owns. An entry is the keyword
  arguments of an app-model `Action`:

  ```yaml
  actions:
    - id: myapp.log.verbose
      title: Verbose logging
      callback: "mylab.contributions:enable_debug_logging"
      menus: [{ id: "myapp/settings" }]
  ```

  A `callback` stays the `module:function` string it was written as, and
  app-model imports it when the command first runs, so reading the section
  imports nothing. The callback's parameters are filled from the session's
  store, which is the store the components were built out of. The registration
  is undone when the session is released.
  `redsun.experimental.session.qt.ActionError` names the entry that cannot be
  made: a section that is not a list, an entry that is not a mapping, an entry
  carrying a key an action does not take, or one app-model refuses.

- `redsun.experimental.ConfirmsClose` and the `confirm_close` hook point. The
  session acts on this point's answer, where it only tells the others what
  happened, and `False` leaves the session running:

  ```python
  class KeepOpenWhileRunning:
      def confirm_close(self) -> bool:
          return not acquisition_is_running()
  ```

  Closing the window is what asks, so the title bar, `close()` and quitting the
  application all reach the point.

  A Qt session that installs no hook there asks about unsaved changes itself,
  offering Save, Discard and Cancel. Cancel keeps the session open, and so does
  a cancelled save dialog. The prompt carries a "don't ask again" box, which
  writes `redsun.experimental.session.qt.ASK_ON_CLOSE` to the settings
  store, so the answer is per user and per machine. A session whose
  `Session.has_changes` reports nothing closes without a word.

- `QtSession.model`, `.app` and `.main_window` - the `app_model.Application`
  named after the session, the toolkit application the session runs on, and the
  `QModelMainWindow` built against that application. All three raise
  `RuntimeError` before `build` and are dropped at release, and two live sessions
  of one name raise `ValueError`. `setModelMenuBar` and `addModelToolBar` fill a
  menu bar and a toolbar from the application's registries:

  ```python
  app = MyApp().build()
  app.main_window.setModelMenuBar({"myapp/file": "File"})
  ```

  `QtSession` builds its components out of the application's injection
  store, so a command registered on the application is filled from the
  components the session built. Constructing a container makes no toolkit
  object: `build` makes all three.

- `Session` carries `__weakref__` among its slots, so a session can be
  referred to weakly, as `aboutToQuit.connect(session.shutdown)` needs.
  Instances still carry no `__dict__`.

- A colour-scheme control on every Qt session, pinned to the right of a toolbar
  of its own behind an expanding spacer. That toolbar is added rather than set
  and holds nothing else, so a menu bar and a view's own toolbar are left alone.
  A `color_scheme` key says which mode to start in:

  ```yaml
  color_scheme: dark
  ```

  `redsun.experimental.session.qt.ColorSchemeMode` is `system`, `light` or
  `dark`, and `ColorSchemeButton` cycles them in that order, calling
  `QStyleHints.setColorScheme` for the last two and `unsetColorScheme` for
  `system`. A session without the key starts at `system`, and the glyph shows
  the mode asked for rather than the scheme in force.
  `ColorSchemeMode.from_config` reads the key, `apply` asks the platform, `next`
  gives the order and `glyph` the character.
  `ColorSchemeButton.pin_to(window, mode)` puts a control on a window built
  outside a session.

- `QtSession.save_layout` and `.restore_layout` - where a user left the
  window. `save_layout` puts `saveGeometry` and `saveState` in the session's
  settings under `window.geometry` and `window.state`, base64 encoded;
  `restore_layout` puts them back once every dock exists,
  and does nothing for a session this user has never run. `run` asks for the
  save as the session ends, so a session built without being shown writes
  nothing. A dock is named after the view it holds, which is what Qt matches a
  saved place against.

- `QtSession` destroys the widgets it built, after every component's own
  `shutdown` and before the application is destroyed. Each view is closed and
  then deleted, and the window goes after the views it docks, leaving
  `main_window` reporting an unbuilt session again. A view is closed before it
  is deleted, so its `closeEvent` runs. A reference held across the shutdown is left wrapping a destroyed widget, and using it raises
  `RuntimeError`.

- `ComponentNotBuilt`, a `WiringError` carrying the `component` a port path
  named. A `wiring:` rule naming a component the build failed on is skipped with
  a warning:

  ```
  Not connecting stage.readback -> panel.on_moved: component 'stage' was not built
  ```

  Every other way of getting a rule wrong stays fatal, a name that was never
  declared included, and a rule that is not a mapping of exactly `from` and `to`
  raises `WiringError` naming the entry's position.

- A component that shares nothing, asks for nothing and is wired to nothing is
  named once the wiring is applied, as is a `provides` return type no component
  asks for. Both are warnings rather than failures. Being injected by another
  component counts as being used, as does answering a `Requires`, `RequiresOne`
  or `RequiresMaybe` question.

### Changed

- The session configuration key `session` is now `name`, in both container
  layers, and identifies the session rather than titling its window. It names
  the session's application, so two sessions in one process must not share it:

  ```yaml
  name: my-session
  frontend: pyqt
  ```

  A container that declares no name is named after its own class, so
  `class Instrument(Session)` builds a session called `Instrument`, and the
  same holds for `AppContainer` in the supported layer.
  `from_config` refuses a file that omits the key, a session built from a
  configuration alone having no class of its own. `RedSunConfig.session` is
  `RedSunConfig.name`, both containers take `name` in place of `session` at
  construction, and `VirtualContainer.session` is `VirtualContainer.name`.

- `app-model` is a dependency of the `qt-common` extra, beside `qtpy` and
  `magicgui`.

- `redsun.experimental.VirtualContainer` is gone, and so is
  `Session.virtual_container`. Its jobs are the session's own:

  | was | is |
  | --- | --- |
  | `virtual_container.connect`, `.connect_paths`, `.connections`, `.unconnected`, `.disconnect_all` | the same names on `Session` |
  | `virtual_container.subscribe`, `.subscriptions` | the same names on `Session` |
  | `virtual_container.satisfying` | `Session.satisfying` |
  | `virtual_container.name`, `.schema_version`, `.frontend`, `.metadata` | ask for `SessionConfig` by type |
  | `virtual_container.register_callbacks`, `.callbacks` | `BlueskyCallbackRegistry` |
  | `virtual_container.on_release`, `.release` | `Session.on_release` and `Session.shutdown` |
  | `virtual_container.register_signals`, `.signals` | removed |

  One teardown runs where there were two. `Session.shutdown` drops the
  connections first, then the releases in the reverse of the order taken, so a
  component is finalized before whatever it was built on.

- The experimental layer's container is a session. The old names are gone, with
  no aliases:

  | was | is |
  | --- | --- |
  | `redsun.experimental.containers` | `redsun.experimental.session` |
  | `redsun.experimental.containers.qt` | `redsun.experimental.session.qt` |
  | `redsun.experimental.containers.container` | `redsun.experimental.session`, the module behind it being private |
  | `redsun.experimental.virtual` | `redsun.experimental.ports`, `.injection` and `.registry` |
  | `AppContainer` | `Session` |
  | `QtAppContainer` | `QtSession` |

  `redsun.containers` and its `AppContainer` are unchanged.

  Each package carries its own public surface: `ports` the connectors a session
  binds, `injection` what a component asks the session for and offers back, and
  `registry` the framework's own values, being the session configuration, the
  device mapping and the bluesky callback registry. `redsun.experimental`
  re-exports all three, and is still the import a component is written
  against.
