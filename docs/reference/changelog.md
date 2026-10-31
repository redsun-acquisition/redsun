---
icon: lucide/history
---

# Changelog

What changed in each release, grouped as in
[Keep a Changelog](https://keepachangelog.com/en/1.0.0/). This project follows
[Semantic Versioning](https://semver.org/spec/v2.0.0.html), and dates are
written `DD-MM-YYYY`.

Each entry links the pull request that made it. A change that breaks
existing code is listed under **Breaking**, and a migration guide such as
[How to migrate from 0.13](../how-to/migrate-from-0.13.md) shows how to move
code across it.
Releases up to 0.13.2 are in the [previous changelog](previous-changelog.md).

<!-- towncrier release notes start -->

## [0.16.0](https://github.com/redsun-acquisition/redsun/releases/tag/v0.16.0) - 31-10-2026

### Breaking

- `redsun.session.BUILD_STEPS` is removed. Code reading it iterates `BuildStep`, which lists the same steps in order. ([#214](https://github.com/redsun-acquisition/redsun/pull/214))
- A view whose class answers `placement` from a property, and whose declaration gives none, is refused and left out; set `placement` as a class attribute or give it in the declaration. ([#214](https://github.com/redsun-acquisition/redsun/pull/214))
- `redsun.presenter.PositionerPresenter` groups axes by the device holding them directly. A device whose axes sit below one of its children, such as `stage.motors.x`, shows them in the box of that child, `stage-motors`, so positions saved under `stage` no longer match and `include: [stage]` keeps no box. ([#219](https://github.com/redsun-acquisition/redsun/pull/219))
- `redsun.utils.devices.find_axes` and `walk_axes` are removed. Code using them walks the device with `walk_devices` of `ophyd-async` and keeps each `Axis` that is not a signal. ([#219](https://github.com/redsun-acquisition/redsun/pull/219))
- A device declared with `service=` whose `prefix` argument defaults to `None` is built without a prefix when its service does not start, where it was skipped before. ([#221](https://github.com/redsun-acquisition/redsun/pull/221))
- A session with `strict` set stops when any service does not start, whether or not a device names it. ([#221](https://github.com/redsun-acquisition/redsun/pull/221))
- A keyboard shortcut declared with `redsun.shortcut` runs its method once per press, however long the key is held, unless it is given `repeat=True`. ([#223](https://github.com/redsun-acquisition/redsun/pull/223))
- `redsun.testing.keep_application_as_found`, and the setting that gives Qt's `offscreen` platform the system fonts on Windows, move to `redsun.testing.qt`. A suite testing Qt components installs the `testing-qt` extra and loads `-p redsun.testing.qt` as well as `-p redsun.testing`. ([#233](https://github.com/redsun-acquisition/redsun/pull/233))
- `redsun.presenter.AcquisitionPresenter.sig_plan_done` no longer reports a plan stopped with `stop`, which `sig_plan_stopped` reports instead. A session file writing out the links of the acquisition stack under `wiring` adds `acquisition.sig_plan_stopped: acquisition_view.set_stopped`. ([#235](https://github.com/redsun-acquisition/redsun/pull/235))
- `PlanProgress.watch` takes a `Watcher` of `ophyd-async`, and a fraction reported alone reaches watchers with `current`, `initial` and `target` left `None`. A followed status that reports no unit gives `unit` as `None` instead of `"unit"`.
- `redsun.engine.ProgressState` is removed. `RunEngine.sig_progress` carries the open `PlanProgress` scopes, whose `update` holds the last `WatcherUpdate` of `ophyd-async`.

### Added

- `redsun.Session.build` warns when components ask for two protocols with the same members, which the same components satisfy. ([#218](https://github.com/redsun-acquisition/redsun/pull/218))
- `redsun.utils.devices.DevicePath`, `device_path` and `held_by` give where a device sits in its tree, such as `microscope / xy.x`, and whether a plan holds it or a device above it. `AxisInfo.path`, `LightInfo.path`, `Configuration.paths` and `ParamDescription.labels` carry those paths to views, which title boxes, rows and device choices with them. ([#219](https://github.com/redsun-acquisition/redsun/pull/219))
- `redsun.Declare(services={...})` and the `services` key of a device's entry give each constructor keyword the prefix of the service it names. A keyword whose service does not start is left out when its default is `None`, and the device is built without that piece. ([#221](https://github.com/redsun-acquisition/redsun/pull/221))
- `redsun.shortcut` takes `repeat=True` to run its method again at the keyboard's repeat rate while the key is held, and `redsun.Shortcut.repeat` records it. ([#223](https://github.com/redsun-acquisition/redsun/pull/223))
- `redsun.Frontend.view_coroutines` says whether a key can run a view's coroutine method. It is false by default and in the Qt frontend, which leave such a key out and log it. ([#226](https://github.com/redsun-acquisition/redsun/pull/226))
- `redsun.shortcut` takes a coroutine method. A presenter's runs on the session's loop without blocking the key press, a press while it still runs is ignored, what it raises is logged, and it is cancelled when the session shuts down, which waits up to 5 seconds for it to stop. ([#226](https://github.com/redsun-acquisition/redsun/pull/226))
- `redsun.qt.styles.qlementine.QlementineStyle` takes `dark` and `light`, paths to `qlementine` theme files used in place of its built-in themes, and `animations=False` to turn its animations off. A key a theme file gives that `qlementine` does not know, or a value of the wrong kind, is logged. ([#227](https://github.com/redsun-acquisition/redsun/pull/227))
- `redsun.services.sharedbox.BoxTransport` serves a `fastcs` controller as one box per controller and an index box describing them, and answers each write with the service's error when the put fails. ([#232](https://github.com/redsun-acquisition/redsun/pull/232))
- `redsun.services.serve_controller` runs a `fastcs` controller as a launched service over the transport it is given, under the session's prefix, and reports the service ready once the transport can be reached. ([#232](https://github.com/redsun-acquisition/redsun/pull/232))
- `redsun.device.sharedbox.BoxDeviceConnector` fills an `ophyd-async` device from the index of a `sharedbox` service, with `BoxSignalBackend` and `BoxCommandBackend` behind its signals and commands. A refused write or a failed command raises `redsun.device.sharedbox.BoxPutError`, and `redsun.device.sharedbox.stream_name` names a stream the service makes itself. ([#232](https://github.com/redsun-acquisition/redsun/pull/232))

  ```python
  class MyDetector(Device):
      exposure: SignalRW[float]

      def __init__(self, prefix: str, name: str = "") -> None:
          super().__init__(name=name, connector=BoxDeviceConnector(prefix))
  ```
- `sharedbox` is a new value of `services.transport`: a session reaches its services through `sharedbox` boxes in shared memory on the same computer, with no network server. The `sharedbox` extra installs `sharedbox` and `fastcs` for it. ([#232](https://github.com/redsun-acquisition/redsun/pull/232))
- `redsun.testing.qt` is a `pytest` plugin for testing Qt components, installed with the `testing-qt` extra. It defines a `qapp` fixture. `emit_queued_on_main_thread` delivers on the main thread the `psygnal` emissions queued from other threads, whichever plugin supplies `qapp`. `release_slots_after_module` releases the slots of the widgets freed after each test module, which `pyqt6` otherwise holds until the process exits. `application_state` returns the stylesheet, style, font and hand-set palette that `keep_application_as_found` compares. ([#233](https://github.com/redsun-acquisition/redsun/pull/233))
- `redsun.presenter.AcquisitionPresenter.sig_plan_stopped` reports a plan stopped with `stop`, and `redsun.view.qt.builtins.AcquisitionView.set_stopped` shows the plan stopped until it runs again. ([#235](https://github.com/redsun-acquisition/redsun/pull/235))
- `redsun.path_provider.SessionPathProvider.set_label` leads the file names of every later plan with a label, as `<label>_<plan>_<counter>`. `redsun.view.qt.builtins.AcquisitionView` has a field for the label, which reaches the provider through the new `redsun.presenter.AcquisitionPresenter.set_label`. ([#236](https://github.com/redsun-acquisition/redsun/pull/236))
- `redsun.device.sharedbox.BoxDeviceConnector` takes `declared_only=True` to fill a device with only the signals, commands and children it declares, so several devices can share one service. ([#238](https://github.com/redsun-acquisition/redsun/pull/238))

  ```python
  class MyCamera(Device):
      exposure: SignalRW[float]

      def __init__(self, prefix: str, name: str = "") -> None:
          super().__init__(
              name=name, connector=BoxDeviceConnector(prefix, declared_only=True)
          )
  ```
- `redsun.AsStack` and a `stacks` section in a session file and a plugin manifest declare a presenter and its views as one stack, which the session builds as `<stack>` and `<stack>_<role>` and pairs. `redsun.view.qt.builtins` ships `AcquisitionStack`, `PositionerStack` and `LightStack`, listed in `redsun`'s manifest as `acquisition`, `positioner` and `lights`. ([#239](https://github.com/redsun-acquisition/redsun/pull/239))

  ```python
  class MyStack:
      presenter: AsPresenter[MyController]
      view: AsView[MyView]


  class MyApp(QtSession):
      my_ctrl: AsStack[MyStack]
      acquisition: AsStack[AcquisitionStack]
  ```
- `PlanProgress` is generic over the type of the values it reports, and `PlanProgress.update` returns its last update. `monitor_progress` returns a `PlanProgress[T]` for a `WatchableAsyncStatus[T]`.

### Changed

- The built-in positioner, light stack and Configuration tabs treat a device a plan locks as locking every device below it, and none above it. ([#219](https://github.com/redsun-acquisition/redsun/pull/219))
- `redsun.DeviceMapping` and `redsun.DevicesOf` hold every device of each declared tree, signals and commands left out, under the names `ophyd-async` gives them, such as `microscope-xy-x`. `DevicesOf` checks each device against its protocol on its own. Two devices with one name, or a device with no name, stop the build with a `BuildError`. ([#219](https://github.com/redsun-acquisition/redsun/pull/219))
- The build summary lists the devices built without a piece, under `Built without`, and the services that did not start, under `Services not started`. ([#221](https://github.com/redsun-acquisition/redsun/pull/221))
- `redsun.qt.QtSession` counts the hook providers it skipped in the failures button of its status bar, which reads `2 failed`, and lists each with the hook points it served. ([#224](https://github.com/redsun-acquisition/redsun/pull/224))
- `redsun.testing.qt.keep_application_as_found` also fails a test that leaves a palette set by hand on the application, and puts the palette back. ([#225](https://github.com/redsun-acquisition/redsun/pull/225))
- `redsun.Session.shutdown` cancels a component's async `shutdown` still running after 5 seconds, logs it, and goes on with the rest. ([#226](https://github.com/redsun-acquisition/redsun/pull/226))
- `redsun` requires `annotated-types>=0.8.0`, `platformdirs>=4.13.5` and `pydantic>=2.14.1`. Its Qt extras require `superqt>=0.9.0`, and its `tiled` extra requires `tiled>=0.2.20`. ([#229](https://github.com/redsun-acquisition/redsun/pull/229))
- `redsun`'s `tiled` extra installs `tiled` and `ome-tiled` on Python 3.14, and requires `ome-tiled>=0.2.1`. ([#230](https://github.com/redsun-acquisition/redsun/pull/230))
- `redsun.testing.build` fails a test with an error at teardown when a session it built is still alive once the test is over. A test that raised is not checked. ([#234](https://github.com/redsun-acquisition/redsun/pull/234))

### Removed

- `redsun.session.BUILD_STEPS`; use `BuildStep`. ([#214](https://github.com/redsun-acquisition/redsun/pull/214))
- Reading a view's `placement` from a property of the built view. ([#214](https://github.com/redsun-acquisition/redsun/pull/214))
- `redsun.utils.devices.find_axes` and `redsun.utils.devices.walk_axes`. ([#219](https://github.com/redsun-acquisition/redsun/pull/219))

### Fixed

- A `redsun.injection.provides` member annotated `X | None` shares its value as `X`. The session now refuses a second component sharing `X`, and no longer logs the value as one no component asks for. ([#217](https://github.com/redsun-acquisition/redsun/pull/217))
- `redsun.DevicesOf[Axis]` holds the axes built on `ophyd-async`'s `StandardMovable`, whose `set` names its parameter `new_position`. `redsun.utils.devices.Axis.set` takes its value by position only. ([#220](https://github.com/redsun-acquisition/redsun/pull/220))
- `redsun.Declare(services={...})` refuses to map `name` or `path_provider`, which the session gives the device itself, when the configuration is read, instead of skipping the device at build. ([#222](https://github.com/redsun-acquisition/redsun/pull/222))
- **Window** -> **Keyboard shortcuts** opens no editor in the second key cell of a command with no key. ([#223](https://github.com/redsun-acquisition/redsun/pull/223))
- **Window** -> **Keyboard shortcuts** clears the message refusing a key at the next key pressed in a cell and at **Reset to defaults**. ([#223](https://github.com/redsun-acquisition/redsun/pull/223))
- `redsun.Session.resolve_shortcuts` logs each conflict between keys the first time it settles it, not at every call. ([#223](https://github.com/redsun-acquisition/redsun/pull/223))
- Escape pressed in a key cell of **Window** -> **Keyboard shortcuts** leaves the key as it was, instead of binding Escape. ([#223](https://github.com/redsun-acquisition/redsun/pull/223))
- `redsun.ConfigurationError` locates a problem in a hook entry that a session file lists at a hook point by its index, such as `hooks.configure_application[1].kwargs`. ([#224](https://github.com/redsun-acquisition/redsun/pull/224))
- The step box of `redsun.view.qt.builtins.PositionerGroup` takes its width from the style, so the step still shows beside a wider arrow, such as the `qlementine` style's. ([#225](https://github.com/redsun-acquisition/redsun/pull/225))
- A task still pending on the shared event loop of `redsun.aio`, such as one started with `redsun.aio.run_coro`, is cancelled when the process exits, and the loop is then stopped and closed. ([#232](https://github.com/redsun-acquisition/redsun/pull/232))
- `redsun.qt.QtSession.shutdown` deletes the actions of the session's menus and releases the slots connected to its widgets, under `pyqt6` too, so neither keeps the session and what it built alive until the process exits. ([#232](https://github.com/redsun-acquisition/redsun/pull/232))
- `redsun.log.BufferHandler` retains each record with its message and traceback as text, and no longer keeps alive the arguments and the exception the record was logged with. ([#234](https://github.com/redsun-acquisition/redsun/pull/234))
- `redsun.services.sharedbox.BoxTransport` builds its controller boxes with `sharedbox` 0.8.0, and the `sharedbox` extra requires `sharedbox` 0.8.0 or later. ([#240](https://github.com/redsun-acquisition/redsun/pull/240))
- `redsun.Session.shutdown` forgets the build when a component's `shutdown` raises, after running every other release, and then raises that error. ([#242](https://github.com/redsun-acquisition/redsun/pull/242))
- `redsun.qt.QtSession.run` delivers the signals queued for the GUI thread every 16 ms, so an idle window leaves the processor idle. ([#242](https://github.com/redsun-acquisition/redsun/pull/242))
- `redsun.view.qt.builtins.AcquisitionView` sends the label in its field when a plan is launched, so a run started while the field still has focus takes the label typed. ([#242](https://github.com/redsun-acquisition/redsun/pull/242))
- `redsun.services.serve_controller` keeps the watchdog that logs every thread's stack when stopping takes over 10 seconds, also when the service is stopped before it is ready. ([#242](https://github.com/redsun-acquisition/redsun/pull/242))
- `redsun.path_provider.SessionPathProvider` resumes the counter of a labelled plan past its files on disk when the label holds a dot, such as `cell1.5`. ([#242](https://github.com/redsun-acquisition/redsun/pull/242))
- A waveform signal of `redsun.device.sharedbox.BoxDeviceConnector`, and a waveform attribute served by `redsun.services.sharedbox.BoxTransport`, raise `ValueError` for a value with another number of dimensions than the waveform, or longer than it. ([#242](https://github.com/redsun-acquisition/redsun/pull/242))
- The `scan_id_source` parameter of `redsun.engine.RunEngine` is annotated without `None`, which failed at the first run.


## [0.15.0](https://github.com/redsun-acquisition/redsun/releases/tag/v0.15.0) - 23-10-2026

### Breaking

- A view whose constructor takes a `placement` keyword is refused, a view declaration reserving `placement` for the session; rename the keyword. ([#172](https://github.com/redsun-acquisition/redsun/pull/172))
- The `pyside` extra installs `pyside6-essentials` instead of the whole `pyside6`, so the PySide6 add-on modules (QtCharts, QtMultimedia, QtSerialPort, QtWebEngine and others) are no longer installed with it; a project using one adds `pyside6` to its own dependencies. A uv-managed environment that had `pyside6` loses files `pyside6-essentials` shares when `uv sync` removes it, and then finds no Qt binding: repair it with `uv sync --reinstall-package pyside6-essentials`, or `pip install --force-reinstall --no-deps pyside6-essentials`. ([#188](https://github.com/redsun-acquisition/redsun/pull/188))
- A test run with `redsun.testing` fails a test that leaves automatic garbage collection on (`keep_automatic_collection_off`); a test ending in an unconditional `gc.enable()` restores the state it found instead. ([#191](https://github.com/redsun-acquisition/redsun/pull/191))
- `Session.hooks` maps every hook point the session calls to a tuple of providers, in the order they run, in place of one provider per installed point. Code reading one provider, such as a frontend calling its own hook point, becomes `(provider,) = session.hooks[point]`; `session.hooks.get(point)` now returns a tuple, so a check of its type against the point's protocol no longer matches. ([#193](https://github.com/redsun-acquisition/redsun/pull/193))
- `ColorSchemeMode.glyph` is removed. Code that showed a mode as text uses the mode itself, which is the text `system`, `light` or `dark`. ([#194](https://github.com/redsun-acquisition/redsun/pull/194))

### Added

- Add `profile="start"` or `profile="run"`, with `profile_dir=`, to `Session`, `redsun.qt.QtSession` and `Session.from_config`, which write a `pyinstrument` timeline of the session's start or run as an HTML file beside its logs. ([#156](https://github.com/redsun-acquisition/redsun/pull/156))
- Add the `profile` extra, with `pyinstrument` and `py-spy`. ([#156](https://github.com/redsun-acquisition/redsun/pull/156))
- Add `timeout=` to `redsun.aio.run_coro`, which cancels the coroutine when the wait ends without a result. ([#161](https://github.com/redsun-acquisition/redsun/pull/161))
- Add `redsun.utils.devices`, with `Axis`, `AxisInfo`, `Configuration`, `limits`, `walk_axes`, `find_axes`, `describe_axis` and `read_configuration`. ([#162](https://github.com/redsun-acquisition/redsun/pull/162))
- Add `redsun.view.qt.treeview.DescriptorTreeView.set_enabled`. ([#162](https://github.com/redsun-acquisition/redsun/pull/162))
- Add `redsun.presenter.PositionerPresenter`, `redsun.presenter.DescribesAxes`, `redsun.view.qt.builtins.PositionerView` and `redsun.view.qt.builtins.PositionerGroup`, registered as the `positioner` presenter and view, which move the axes of any device by hand: steps, a go-to field per axis, Stop, saved positions and a Configuration tab. ([#162](https://github.com/redsun-acquisition/redsun/pull/162))
- Add `redsun.aio.cancel_task`, which cancels a task from any thread and leaves alone a task that has finished its work. ([#163](https://github.com/redsun-acquisition/redsun/pull/163))
- Add `Readback`, `readback` and `Configuration.owners` to `redsun.utils.devices`, and an `owners` keyword to `redsun.view.qt.treeview.DescriptorTreeView`. ([#164](https://github.com/redsun-acquisition/redsun/pull/164))
- Add `redsun.presenter.DeviceConfiguration` and `redsun.view.qt.treeview.ConfigurationTab`, which read, follow and edit a device's configuration. ([#164](https://github.com/redsun-acquisition/redsun/pull/164))
- Add `redsun.presenter.LightPresenter`, `redsun.presenter.DescribesLights`, `redsun.view.qt.builtins.LightView` and `redsun.view.qt.builtins.LightGroup`, registered as the `lights` presenter and view, which switch lights on and off and set their intensity. ([#164](https://github.com/redsun-acquisition/redsun/pull/164))
- Add the `Light` and `DimmableLight` protocols to `redsun.utils.devices`, a device whose `enabled` is a boolean signal it can write, with an optional numeric `intensity`, and `LightInfo`, `describe_light`, `dimmable` and `is_light` beside them. ([#164](https://github.com/redsun-acquisition/redsun/pull/164))
- Add the `HasActions` protocol. ([#165](https://github.com/redsun-acquisition/redsun/pull/165))
- Add `redsun.engine.RunEngine.cancel_pause`, which withdraws a deferred pause no checkpoint has reached. ([#165](https://github.com/redsun-acquisition/redsun/pull/165))
- Add `redsun.presenter.AcquisitionPresenter`, `redsun.presenter.DescribesPlans` and `redsun.view.qt.builtins.AcquisitionView`, registered as the `acquisition` presenter and view, which run the plans the session's components offer and share the presenter's `RunEngine` and `Deferrals` with any component that asks for them. ([#165](https://github.com/redsun-acquisition/redsun/pull/165))
- Add `redsun.presenter.utils.device_class`. ([#165](https://github.com/redsun-acquisition/redsun/pull/165))
- Add a `pairs:` section to the session file, where `[a, b]` connects every link between two components, in both directions. ([#168](https://github.com/redsun-acquisition/redsun/pull/168))
- Add `links_between`, in `redsun.ports` and `redsun`, which yields the links between two components for a `wire` method. ([#168](https://github.com/redsun-acquisition/redsun/pull/168))
- Add `signal=` to `slot`, naming the signals of another component that reach the slot in a pairing. ([#168](https://github.com/redsun-acquisition/redsun/pull/168))
- Add plan widget inputs for mappings, sets, fixed-length tuples, optional values and unions, nested to any depth. ([#169](https://github.com/redsun-acquisition/redsun/pull/169))
- Add a `placement` key to a view's declaration and its session file entry; Qt reads `left`, `right`, `top`, `bottom`, `central`, `{dock: <edge>, group: <name>}`, `{menu: <name>}` and `{toolbar: <name>}`. ([#172](https://github.com/redsun-acquisition/redsun/pull/172))
- Add `group=` to `redsun.qt.Dock`, which tabs the docks of one edge and group together. ([#172](https://github.com/redsun-acquisition/redsun/pull/172))
- Add checks of plan parameter values against their `annotated-types` limits, at any level: a plan whose default breaks its limits is refused, so is a launch with a value outside them, and the plan widget's inputs keep to the limits. ([#173](https://github.com/redsun-acquisition/redsun/pull/173))
- Add a Window menu to the Qt window, `redsun.qt.WINDOW_MENU`, with a toggle for each dock and Reset layout. ([#178](https://github.com/redsun-acquisition/redsun/pull/178))
- Add `Session.resolve_layout()`, and `Frontend.regions`, `Frontend.hides`, `Frontend.region_of` and `Frontend.layout_problems`. ([#179](https://github.com/redsun-acquisition/redsun/pull/179))
- Add `WindowLayout`, `Row`, `Column` and `Tabs`, declared through `Session.window_layout()` or a `layout:` section of the session file, to set a window's first layout: what fills each region, shares of the window, and docks that start hidden. ([#179](https://github.com/redsun-acquisition/redsun/pull/179))
- Add `redsun.qt.QtSession.show()`, which `run` calls, and `layout=` to `redsun.qt.attach`; the Qt session saves the centre's splitters and tabs as `window.center`. ([#179](https://github.com/redsun-acquisition/redsun/pull/179))
- Add `redsun.session.BuildStep`, the steps a build reports, in order. ([#180](https://github.com/redsun-acquisition/redsun/pull/180))
- Add a `shortcuts:` section to the session file, giving a command named `<component>.<method>`, or a session file action, other keys or none; a key two commands ask for in one place stays with the first declared, and `strict` stops the build instead. ([#184](https://github.com/redsun-acquisition/redsun/pull/184))
- Add Window -> Keyboard shortcuts to the Qt window, listing every bound key by view, and `Frontend.key_problems` and `Frontend.canonical_key`. ([#184](https://github.com/redsun-acquisition/redsun/pull/184))
- Add `redsun.shortcut`, a decorator marking a presenter or view method that a key runs, in the whole window or with `scope="view"` only while the component's view has focus. ([#184](https://github.com/redsun-acquisition/redsun/pull/184))
- Add `AcquisitionView.run_plan` on `Ctrl+R` and `AcquisitionView.stop_plan` on `Ctrl+.`. ([#185](https://github.com/redsun-acquisition/redsun/pull/185))
- Add `PositionerView.step_down` and `PositionerView.step_up` on Left and Right, acting on the focused axis, and `PositionerGroup.focused_axis` and `PositionerGroup.step`. ([#185](https://github.com/redsun-acquisition/redsun/pull/185))
- Add `when=` to `redsun.shortcut`: the key acts only while a function of the component returns true, and otherwise goes to the focused widget. ([#185](https://github.com/redsun-acquisition/redsun/pull/185))
- Window -> Keyboard shortcuts edits keys: double-click a key cell and press the new key, Backspace or Delete to clear it; a key another command holds moves after the user agrees; Reset to defaults forgets the changes. ([#186](https://github.com/redsun-acquisition/redsun/pull/186))
- Add `Session.set_shortcuts` and `Session.reset_shortcuts`, keeping the user's keys in the session's settings and applying them over the session file's `shortcuts:` section; a saved key wins over a component's default. ([#186](https://github.com/redsun-acquisition/redsun/pull/186))
- Add `redsun.qt.QtSession.garbage_interval`, the milliseconds between two checks of Python's garbage while a Qt session runs, 100 by default. ([#187](https://github.com/redsun-acquisition/redsun/pull/187))
- Add `redsun.qt.styles.napari.NapariStyle`, a `configure_application` hook provider giving the window the stylesheet and icons of `napari` 0.9.2, dark or light as the colour scheme reads, and switching with it; a session file installs it as `configure_application: napari`. ([#190](https://github.com/redsun-acquisition/redsun/pull/190))
- Add short names for the hook providers `redsun` ships: a `hooks` entry in a session file names one alone (`configure_application: napari`) or as `provider: napari`, and `redsun`'s manifest lists them under a new `hooks` key. ([#190](https://github.com/redsun-acquisition/redsun/pull/190))
- Add `redsun.Many`: a hook point declared with it takes several providers, run in order, the class's first and then the session file's; `configure_application`, `configure_main_view` and `during_build` of `redsun.qt.QtSession` take several, and a hook point in a session file holds one entry or a list. ([#193](https://github.com/redsun-acquisition/redsun/pull/193))
- Add `Session.call_hooks` and `Session.skip_hook`, for a frontend calling its hook points. ([#193](https://github.com/redsun-acquisition/redsun/pull/193))
- Add `redsun.testing.keep_application_as_found`, failing a test using `qapp` that leaves the application's stylesheet, style or font changed. ([#193](https://github.com/redsun-acquisition/redsun/pull/193))
- Add `font_size` to `redsun.qt.styles.napari.NapariStyle`, the base size of its stylesheet in points. ([#193](https://github.com/redsun-acquisition/redsun/pull/193))
- Add the `redsun` command, installed with the package: `redsun --example` opens a session holding every built-in component over simulated devices, and `redsun --example napari` opens it in the `napari` style. `redsun.examples.ExampleApp` is that session. ([#195](https://github.com/redsun-acquisition/redsun/pull/195))
- Add `redsun.qt.styles.qlementine.QlementineStyle`, a `configure_application` hook provider giving a Qt session `qlementine`'s look, in its dark or light theme as the colour scheme reads; a session file names it `qlementine`, and `redsun --example qlementine` shows it. The `qlementine-pyqt` and `qlementine-pyside` extras install the package it needs. ([#196](https://github.com/redsun-acquisition/redsun/pull/196))
- Add `redsun.view.qt.icons`: `set_icon`, `set_item_icon`, `collapsible_section` and `set_collapsible_icons` put the icons of the built-in views on a view of your own, following its palette through a change of colour scheme. ([#197](https://github.com/redsun-acquisition/redsun/pull/197))
- Add `redsun.view.qt.builtins.LogWindowAction`, a **Logs** entry in the **View** menu that opens the log view in a window of its own, offered by the `redsun` plugin as `log-window`. ([#211](https://github.com/redsun-acquisition/redsun/pull/211))

### Changed

- `redsun.aio.run_coro` refuses to block on the shared loop's own thread, and accepts any awaitable, not only a coroutine. ([#161](https://github.com/redsun-acquisition/redsun/pull/161))
- The Qt extras install `superqt`. ([#162](https://github.com/redsun-acquisition/redsun/pull/162))
- A `create_application` hook that returns anything but a `QApplication` is refused with a `HookError` naming its provider. ([#167](https://github.com/redsun-acquisition/redsun/pull/167))
- The `config_home` fixture of `redsun.testing` applies to every test, under `tmp_path / "config"`. ([#167](https://github.com/redsun-acquisition/redsun/pull/167))
- A plan parameter no input can show is hidden and given its default, and Run stays disabled while an input is invalid, with the reason shown. ([#169](https://github.com/redsun-acquisition/redsun/pull/169))
- A number input with no limit takes any value, not only 0 to 999. ([#173](https://github.com/redsun-acquisition/redsun/pull/173))
- A saved dock layout is skipped, with a log line saying why, once a view's placement changes; the settings file records the placements as `window.layout`. ([#178](https://github.com/redsun-acquisition/redsun/pull/178))
- The positioner's Left and Right are keyboard shortcuts, listed under Window -> Keyboard shortcuts and changed in the session file's `shortcuts:` section. ([#185](https://github.com/redsun-acquisition/redsun/pull/185))
- The `pyside` extra accepts PySide6 from 6.10.2, and both Qt extras skip Qt 6.11.0 and 6.11.1, which resize dock widgets wrongly. ([#188](https://github.com/redsun-acquisition/redsun/pull/188))
- The plan, positioner and light buttons of the built-in views and the colour scheme control show icons from the Material Design icon font in place of text, coloured from the palette so they follow light and dark, with their words in the tooltip and the accessible name; the log view's level selector shows an icon beside each level. `fonticon-materialdesignicons7` is a new dependency of the Qt extras. ([#189](https://github.com/redsun-acquisition/redsun/pull/189))
- `redsun.testing` turns Python's automatic garbage collection off for the whole test run (`no_automatic_collection`) and collects after each test module on the main thread (`collect_after_module`); a test that needs an object in a reference cycle freed calls `gc.collect()` itself. ([#191](https://github.com/redsun-acquisition/redsun/pull/191))
- A hook provider that cannot be built, or whose hook raises, is logged, skipped and listed in the build summary; a failed `create_application` provider still stops the build, and `strict` stops it on any. ([#193](https://github.com/redsun-acquisition/redsun/pull/193))
- A plugin manifest with a `hooks` section is left out: only `redsun` ships short hook names. ([#193](https://github.com/redsun-acquisition/redsun/pull/193))
- `Session` logs a shared value no component asks for at debug level, not as a warning. ([#210](https://github.com/redsun-acquisition/redsun/pull/210))

### Deprecated

- A view class answering `placement` from a property, removed in 0.16; give `placement` in the declaration instead. ([#172](https://github.com/redsun-acquisition/redsun/pull/172))
- `redsun.session.BUILD_STEPS`, removed in 0.16; use `BuildStep`. ([#180](https://github.com/redsun-acquisition/redsun/pull/180))

### Removed

- The log lines naming the docks a saved layout kept away from their placements. ([#178](https://github.com/redsun-acquisition/redsun/pull/178))
- `ColorSchemeMode.glyph`, the character that stood for a mode in plain text. ([#194](https://github.com/redsun-acquisition/redsun/pull/194))

### Fixed

- `Settings` refuses a value it cannot store as JSON, and keeps its other values. ([#158](https://github.com/redsun-acquisition/redsun/pull/158))
- An edit in `redsun.view.qt.treeview.DescriptorTreeView` to a setting that belongs to no device no longer raises. ([#158](https://github.com/redsun-acquisition/redsun/pull/158))
- A cancelled deferred change is dropped, and the changes queued after it are still applied. ([#158](https://github.com/redsun-acquisition/redsun/pull/158))
- A session can be built again after `shutdown`. ([#158](https://github.com/redsun-acquisition/redsun/pull/158))
- A malformed `providers` entry in a session file is refused, and one naming no plugin is logged. ([#158](https://github.com/redsun-acquisition/redsun/pull/158))
- A failed write of `Settings` keeps the previous settings. ([#162](https://github.com/redsun-acquisition/redsun/pull/162))
- A component that subclasses a dataclass from another module no longer fails to resolve its fields' annotations. ([#162](https://github.com/redsun-acquisition/redsun/pull/162))
- Closing a session that launched services no longer prints a Channel Access circuit disconnect. ([#162](https://github.com/redsun-acquisition/redsun/pull/162))
- A plan parameter annotated with a protocol given type arguments, such as `Readable[Any]`, is matched to devices. ([#165](https://github.com/redsun-acquisition/redsun/pull/165))
- The `build` fixture of `redsun.testing` shuts down every session it made when one refuses, raising every error together. ([#167](https://github.com/redsun-acquisition/redsun/pull/167))
- `redsun.view.qt.builtins.LogView` redraws in the colours of the palette just applied, its console included. ([#167](https://github.com/redsun-acquisition/redsun/pull/167))
- A link that `wire` and `wiring:` both name is made once. ([#168](https://github.com/redsun-acquisition/redsun/pull/168))
- The plan widget keeps list, tuple and `None` defaults, and reads `Annotated` metadata at every level without refusing the plan. ([#169](https://github.com/redsun-acquisition/redsun/pull/169))
- On POSIX, a service blocked in a system call stops at once when the session asks it to stop. ([#171](https://github.com/redsun-acquisition/redsun/pull/171))
- A settings file whose saved layout cannot be read is logged, and the docks start from their placements. ([#179](https://github.com/redsun-acquisition/redsun/pull/179))
- Locking a positioner device keeps the focus on its own row, so a held arrow key no longer steps another device. ([#185](https://github.com/redsun-acquisition/redsun/pull/185))
- `Session.shutdown` returns once the background dispatch of coroutine slots has stopped and cancelled its pending callbacks, so nothing it logs or runs comes after it returns. ([#187](https://github.com/redsun-acquisition/redsun/pull/187))
- A Qt session runs Python's automatic garbage collection on the GUI thread only, so a widget freed by an automatic collection on a background thread no longer aborts a `pyside6` application. ([#187](https://github.com/redsun-acquisition/redsun/pull/187))
- The positioner view's Saved positions header redraws its arrow when the colour scheme changes, so the arrow stays visible after switching between light and dark. ([#190](https://github.com/redsun-acquisition/redsun/pull/190))
- `redsun.view.qt.builtins.LogView` drops the redraw a palette change asked for when the view is deleted first. Under `pyside6` that redraw ran on the deleted view and raised an error. ([#195](https://github.com/redsun-acquisition/redsun/pull/195))
- The positioner view's Saved positions section is built without Qt's `QPainter` warnings under a font sized in pixels, which the `qlementine` style sets. ([#197](https://github.com/redsun-acquisition/redsun/pull/197))
- `collect_arguments` (`redsun.presenter.plan_spec`) gives a positional parameter with no value its default when a later positional argument is given, and raises `ValueError` when it has no default. A plan launched with only some of its values had every later positional value one place to the left. ([#202](https://github.com/redsun-acquisition/redsun/pull/202))
- `QtSession.show` grows the window on its first show to the size its views ask for once the style has reached them, so a dock no longer opens narrower than its content. ([#210](https://github.com/redsun-acquisition/redsun/pull/210))


## [0.14.3] - 01-10-2026

### Added

- Add service process functions, args mapping and Attach address ([#153](https://github.com/redsun-acquisition/redsun/pull/153))

## [0.14.2] - 30-09-2026

### Added

- Show plan progress, following device statuses ([#151](https://github.com/redsun-acquisition/redsun/pull/151))

### Fixed

- Name the accepted transports, accept pytest 8 in the testing extra ([#149](https://github.com/redsun-acquisition/redsun/pull/149))
- Log the configuration sources and hook points one per line ([#150](https://github.com/redsun-acquisition/redsun/pull/150))

## [0.14.1] - 30-09-2026

### Added

- Add `redsun.testing`, fixtures for testing a plugin ([#147](https://github.com/redsun-acquisition/redsun/pull/147))

### Fixed

- List a service again once its address list is cleared ([#145](https://github.com/redsun-acquisition/redsun/pull/145))

## [0.14.0] - 29-09-2026

### Changed

- **Breaking:** Replace the container layer with sessions ([#85](https://github.com/redsun-acquisition/redsun/pull/85))

[0.14.0]: https://github.com/redsun-acquisition/redsun/compare/v0.13.2...v0.14.0
[0.14.1]: https://github.com/redsun-acquisition/redsun/compare/v0.14.0...v0.14.1
[0.14.2]: https://github.com/redsun-acquisition/redsun/compare/v0.14.1...v0.14.2
[0.14.3]: https://github.com/redsun-acquisition/redsun/compare/v0.14.2...v0.14.3
