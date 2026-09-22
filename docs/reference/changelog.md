# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Dates are specified in the format `DD-MM-YYYY`.

## [Unreleased]

### Added

- **`Deferrals`** and **`DEFERRALS`** (`redsun.engine`) - a change to apply
  between two messages of a running plan. `Deferrals(engine)` installs a
  suspender; `request(apply)` queues a coroutine function, applied on the
  engine's loop once the message under way completes, or at once when no
  plan runs. A change that raises is logged and the rest still run. The
  engine's owner provides it under `DEFERRALS`.

- **`Service`**, **`STARTUP_TIMEOUT`** and **`STOP_TIMEOUT`** (`redsun.services`) - the handle a
  container makes for each service it declares. A service with a module runs
  as `python -m <module> <args>`: `start` waits up to `STARTUP_TIMEOUT` seconds
  for its readiness line, logs its output at `DEBUG` on
  `redsun.service.<name>`, launches it with `REDSUN_SERVICE_NAME` and
  `REDSUN_SERVICE_PREFIX` in its environment, and arranges the session's
  transport for it: a Channel Access server port of its own appended to
  `EPICS_CA_ADDR_LIST`, or a PVAccess server on `127.0.0.1` and a free TCP
  port with that address in `EPICS_PVA_ADDR_LIST`. `stop` closes the process's standard
  input, then sends `SIGINT` on POSIX, then kills it, each step waiting
  `stop_timeout` seconds, `STOP_TIMEOUT` (10 s) by default. A ready service exiting unasked logs its exit code
  and last 20 output lines at `ERROR` and emits `sig_exited(name, code)`. A
  service without a module is attached to and has nothing to start or stop.
- **`declare_service`** (`redsun.containers`, `redsun`) - declares a service on
  a container. One with a `module` is launched as `python -m <module> <args>`;
  one without only lends its `prefix`:

  ```python
  class MyApp(AppContainer):
      camera_ioc = declare_service(
          module="mylab.iocs.camera", ready="Server startup complete.", prefix="CAM:"
      )
      camera = declare_device(MyCamera, service="camera_ioc")
  ```

- **`service`** keyword of a device declaration - names the service whose
  prefix the device is built with, passed as `prefix`. Giving `prefix` as well,
  or naming a service for a device whose constructor takes a `service` keyword
  of its own, is refused at declaration. A device naming a service that did not
  start, one that is not declared, or one that gives no prefix, is logged and
  skipped by the build.
- **`AppContainer.start_services`** and **`AppContainer.services`**
  (`redsun.containers.container`) - start every launched service, logging
  `Services started: <n>/<m>` and the ones that did not start; and the
  container's services by name. `build` calls `start_services` as well; only the
  first call before `shutdown` starts anything.
- A `services` section in a session file, and a `services` group in a plugin
  manifest giving a service's `module` and `ready` line. A session entry with
  `plugin_name` and `plugin_id` takes both from the manifest; one without is
  attached to:

  ```yaml
  services:
    camera_ioc:
      plugin_name: mylab
      plugin_id: camera-ioc
      prefix: "CAM:"
      stop_timeout: 60
    beamline:
      prefix: "BL01:"
  ```

- A `transport` key in the `services` section, and **`AppContainer.transport`**
  beside it, naming what every service of the session speaks: `channel-access`,
  the default, or `pv-access`. A transport `redsun` does not have, a component
  named `transport`, and two layered files naming different transports are each
  refused as the container class is created:

  ```yaml
  services:
    transport: pv-access
    camera_ioc:
      plugin_name: mylab
      plugin_id: camera-ioc
  ```

- The build summary names a service whose every device failed to build:
  `Unused: camera_ioc (no device built)`.
- An `epics` dependency group, with `caproto` and `ophyd-async[ca]`, and a
  `pva` one with `p4p` and `ophyd-async[pva]`. Both are for running the tests;
  `redsun` requires `ophyd-async` alone and a component brings what its own
  service speaks.
- **`autoconnect`** keyword of a device declaration, true unless given - whether
  the build connects the device. The build connects every such device at once,
  in a `"connect"` step between devices and presenters, waiting up to
  `CONNECT_TIMEOUT` (`redsun.containers.container`, 10 s) for each. A device
  that does not connect is logged and skipped, listed as
  `<name> (device, not connected)` in the build summary, with the service it
  talks to named in the message.
- **`service_of`** (`redsun.log`) - the name of the service a record came from,
  `None` for the application.
- **`BufferHandler.service_records`**, **`BufferHandler.services`** and
  **`BufferHandler.service_capacity`** (`redsun.log`) - one service's retained
  records or every service's merged by time, the services that have logged,
  and how many records of each are retained, 2 000 by default.
- A launched service's log file, `<run>.<service>.log` beside the
  application's, opened by the container and created once the service logs
  something. `SessionFileHandler` takes a `service` and a `run`, and
  `SessionFileHandler.run` names the run a file belongs to; `add_handler`,
  `remove_handler` and `session_log` take a `service`.
- A line of a service's output that is a JSON log record, written by a stdlib
  formatter or by `loguru` with `serialize=True`, is logged with its own level,
  time and traceback under `redsun.service.<service>.<logger>`; so is a line
  `pvxs` writes, `<time> <LEVEL> <logger> <message>`, with its level, time
  and logger.
- **`LogView`** (`redsun.view.qt.builtins`) shows services' records on a
  Services tab, with a selector for one service or all of them.
- **`SessionPathProvider`**, **`PlanFilenameProvider`** and
  **`session_directory`** (`redsun.path_provider`), moved from
  `redsun.storage`. `session_directory(session)` returns
  `<base_dir>/<session>`.
- **`path_provider`** keyword of a device declaration, reserved by the
  container: a device whose constructor takes it gets the session's provider,
  and a declaration giving one is refused:

  ```python
  class Camera(Device):
      def __init__(self, name: str, path_provider: PathProvider) -> None: ...
  ```

- **`AppContainer.path_provider`** (`redsun.containers.container`) - the
  session's provider, wired under **`PATH_PROVIDER_PORT`**
  (`"path_provider"`), with `set_plan`, `reset_plan` and `set_base_dir` as
  slots:

  ```yaml
  wiring:
    - from: acquisition.sig_pre_launch_notify
      to: path_provider.set_plan
  ```

- **`StorageConfig`** and **`CatalogConfig`** (`redsun.containers`) and a
  `storage` section in a session file: `base_dir`, the root a session writes
  under (`user_data_dir("redsun", appauthor=False)` by default), `max_digits`,
  the width of the file counter, and `catalog`, which, even empty, gives the
  session a catalog in `<base_dir>/<session>/catalog` and needs the `tiled`
  extra:

  ```yaml
  storage:
    base_dir: "D:/experiments/2026-09"   # optional
    catalog:                             # optional
      readable:                          # optional, added to <base_dir>/<session>
        - /data/aht
  ```

  `AppContainer.storage` gives the section after the build. `readable` adds
  directories the catalog may read from. Unknown keys are refused, and so is a
  `catalog` without the `tiled` extra.

- **`SessionPathProvider.session_dir`** (`redsun.path_provider`) - the
  session's directory inside `base_dir`, holding its files and catalog.
- **`SessionPathProvider.lock_base_dir`** (`redsun.path_provider`) - makes
  every later `set_base_dir` raise `RuntimeError` with the given reason. A
  session with a catalog locks its provider once the catalog starts.
- **`SessionPathProvider.base_dir`** and **`SessionPathProvider.set_base_dir`**,
  a slot taking a `str` or a `Path`, effective from the next request. It raises
  `RuntimeError` while a plan runs.
- **`PATH_PROVIDER`** (`redsun.path_provider`) - key the container binds the
  session's provider to:

  ```python
  provider = container.require(PATH_PROVIDER)
  ```

- **`Writer`** (`redsun.writers`) - writes the products a component
  computes against the stores a run names. A product is declared before the
  run, `derive(data_key, source=)` to take its layout and store from the
  `descriptor` and `stream_resource` naming *source*, or `declare(data_key,
  shape=, dtype=, store=)` to give both; the component forwards every
  document with `writer(name, doc)` and hands the data over with
  `append(data_key, data)` per frame or `write(data_key, data, metadata=None)`
  for the whole product, which returns the product's URI:

  ```python
  writer = Writer()
  writer.derive("det_median", source="det")
  ...
  writer.write("det_median", median, metadata={"derived_from": "det"})
  ```

  A product goes as a key of the store the acquisition wrote, or as a store of
  its own beside a root carrying OME-Zarr metadata, named
  `<store>_<data_key>.ome.zarr` and written whole. A run's `stop` closes the
  streams opened for it and writes two mappings on each product's group: *metadata* as given, and
  `redsun` with `run_start`, `source`, `resource_uri` and `written`.
  `shutdown` closes what a session ending mid-run left open.
- **`ArrayShape`** (`redsun.writers`) - the shape and dtype of one
  frame of a product.
- **`WriterError`** (`redsun.writers`) - raised for a product not
  declared, one without its layout or store yet, one declared after its
  store's stream opened, a store the writer cannot take, or an array with too
  few or too many dimensions. Importing the package without `acquire-zarr`
  raises `ImportError` naming the extra that installs it; writing beside an
  OME-Zarr image without `ome-writers` does the same on first use.
- A `zarr` extra and dependency group, with `acquire-zarr`, and an
  `ome-zarr` one, with `ome-writers[acquire-zarr]`.
- A `tiled` extra and dependency group, with `tiled[client,server]` and
  `ome-tiled[bluesky]`. It installs nothing on Python 3.14.
- **`CatalogAddress`** and **`CATALOG`** (`redsun.catalog`) - where a
  session's catalog is served, and its key. `CatalogAddress.uri` carries the
  API key, which the `repr` leaves out. The module imports nothing from
  `tiled`:

  ```python
  from redsun.catalog import CATALOG
  from tiled.client import from_uri

  address = container.try_require(CATALOG)  # None without a catalog
  client = from_uri(address.uri) if address else None
  ```

- A session whose `storage` section has a `catalog` starts a `tiled` server
  with its virtual container, provides its address under `CATALOG`, and stops
  it on `shutdown` after the presenters. The server keeps its database in
  `<base_dir>/<session>/catalog` and reads assets from `<base_dir>/<session>`
  and every `readable` directory, checked on read. A catalog that fails to
  start is logged and skipped. `application/x-ome-zarr` assets are read with
  `ome-tiled`'s `OmeZarrAdapter`, and `ome-tiled`'s consolidator is registered
  for `TiledWriter`, which then stores an OME-Zarr image with its store's
  shape and axis names.


### Changed

- **`DescriptorTreeView`** (`redsun.view.qt`) groups rows by their
  `name-property` key rather than by the descriptor's `source`: one header
  per device name, and one under it per group a property names with a dash of
  its own, `cam-properties-Binning` as `Binning` under `properties` under
  `cam`. A source ending in `:readonly` still greys the row.

- A container class taking a session file gets the services that file
  declares, as it already got its devices, presenters and views. A service
  named in both the file and the class body is the class body's:

  ```python
  class MyApp(AppContainer, config="session.yaml"):
      camera = declare_device(MyCamera, service="camera_ioc")  # declared in the file
  ```

  Before, only `AppContainer.from_config` read the `services` section, so a
  class-based session had to repeat every service in its body or its devices
  were skipped with `service '<name>' is not declared`.

- A session's data, catalog and log folders take the session name with each
  run of characters other than letters, digits, `.`, `-` and `_` replaced by
  `_` and outer dots removed: `Lab A: STED` becomes `Lab_A_STED`. The data
  folder used the name unchanged; earlier files stay where they are.
- **`AppContainer.BUILD_STEPS`** (`redsun.containers.container`) starts with
  `"services"`, so a `during_build` hook reports services starting, and has
  `"connect"` after `"devices"`. A build that raises stops the services before
  the exception propagates.
- **`AppContainer.run`** no longer calls `connect_devices`; the build connects
  the devices declared with `autoconnect`. `connect_devices` connects every
  device, whatever its `autoconnect` says.
- A service keeps its Channel Access server port for as long as the process
  runs, and a container stopping the services it launched closes the process's
  Channel Access channels, so a container built again in the same process
  reaches its services at once.
- **`AppContainer.shutdown`** stops the container's services, the last declared
  first, whether or not the container was built, and before it closes the
  session log file.
- **`BufferHandler`** (`redsun.log`) retains application records and each
  service's records apart, each dropping its oldest once full.
  `BufferHandler.records` holds the application's records only.
- **`SessionFileHandler`** (`redsun.log`) for the application no longer writes
  services' records, and pruning old runs counts a run's service files with it.
- **`GlobalFormatter`** (`redsun.log`) leaves out the location of a record that
  carries none, such as one rebuilt from a service's output.
- **`LogView`** (`redsun.view.qt.builtins`): `Save logs...` and
  `Clear log window` act on the tab shown.
- **`SessionPathProvider`** gives each data key its own directory,
  `<base_dir>/<session>/<YYYY-MM-DD>/<datakey>/<plan>_<counter>`, counting per
  `(plan, datakey)`. A call without a data key leaves that level out.
  **`PlanFilenameProvider.bump`** takes the data key as its second argument
  and **`PlanFilenameProvider.reset`** takes `(plan, datakey)` keys.
- **`SessionPathProvider`** writes under
  `user_data_dir("redsun", appauthor=False)` rather than `~/redsun-storage`.
  Nothing is moved; a provider built while `~/redsun-storage` exists logs a
  `WARNING` naming both locations.

### Removed

- **`DescriptorTreeView.get_keys`** (`redsun.view.qt`), which nothing called.
- **`HasAsyncShutdown`** and the `redsun.device` package, which held nothing
  else. No container ever called `shutdown` on a device.
- The `redsun.storage` shim: **`BaseStorage`**, **`StreamSpec`**,
  **`OpenStore`**, **`StorageIO`**, **`SinkFactory`**, **`StoreStateError`**,
  **`FrameSink`**, **`PathSignals`**, the storage registry
  (**`register_storage`**, **`get_storage`**, **`clear_registry`**,
  **`reset_group`**) and the `acquire-zarr` and in-memory backends; see
  [ADR 0013](../explanation/decisions/0013-acquisition-storage-belongs-to-the-device.md).
  `StreamDatum` ranges are whatever the device emits.
- **`StoragePresenter`** (`redsun.presenter.builtins`) and **`StorageView`**
  (`redsun.view.qt.builtins`), with their manifest entries. A session
  declaring them drops both and gives `base_dir` in the `storage` section.
  `redsun.storage.PATH_PROVIDER` moves to `redsun.path_provider`.
- The `redsun.storage` package. `Writer` lives in `redsun.writers`.
- The `zarr` extra and dependency group require `acquire-zarr` 0.10.0 or
  later, the first release whose arrays take `is_ngff`.

### Changed (breaking)

- **`AppContainer.build`** (`redsun.containers.container`) constructs a device
  as `cls(name=<name>, **kwargs)` rather than `cls(<name>, **kwargs)`. A device
  subclassing `ophyd_async.epics.core.EpicsDevice`, whose first parameter is
  `prefix`, can be declared with `declare_device(MyCamera, prefix="CAM:")`. A
  device constructor taking `name` positional-only fails to build; drop the `/`:

  ```python
  class MyMotor(StandardReadable):
      def __init__(self, name: str, *, egu: str = "mm") -> None: ...
  ```

### Fixed

- **`Deferrals.request`** (`redsun.engine`) raises its flag on the engine's
  loop, and applies a change asked for while no plan runs on that loop too,
  rather than on the caller's. Raised from the caller's thread, the
  suspender gave the engine's loop 0.1 s to make its event and raised
  `Could not create the suspender event` on a busy machine.

- **`DescriptorTreeView`** (`redsun.view.qt`) greys a row whose source ends
  in `:readonly` whatever comes before it, `pva://cam:readonly` included, as
  the docs said; only `soft://readonly` did before.

- **`create_plan_spec`** (`redsun.presenter.plan_spec`) no longer refuses a
  parameter whose default is an empty string, tuple or list as an action
  list it is not annotated for.
- **`create_plan_spec`** (`redsun.presenter.plan_spec`) accepts a plan from a
  module without `from __future__ import annotations`. Its annotations are
  already evaluated, and were re-read as text naming what the module never
  imported, which skipped every plan in it.
- **`create_plan_spec`** (`redsun.presenter.plan_spec`) keeps a `Literal`'s
  values as they are, so `Literal[1, 2, 3]` offers integers and the plan
  receives one. They were turned into strings, which refused the default in
  `create_plan_widget` and handed the plan `"1"`.
- **`AppContainer.build`** (`redsun.containers`) survives a component whose
  `register_providers` or `inject_dependencies` raises: the component is
  logged and dropped, as one failing to build is, rather than ending the
  build. A view asking for what a skipped presenter would have provided no
  longer takes the session down with it.
- **`DescriptorTreeView`** (`redsun.view.qt`) sends a number once it is
  entered, on Enter or focus out. Every keystroke sent a value before, so
  typing `100` wrote 1, 10 and 100 to the device, and a failed write was
  reverted to 10 rather than to the value before the edit.
- **`Service.stop`** (`redsun.services`) on Windows kills a process still
  running after `stop_timeout` at once, as documented, rather than waiting a
  second `stop_timeout` for a signal it never sends.
- **`create_plan_widget`** (`redsun.view.qt.utils`) shows a `bool`
  parameter's name once. `magicgui` gives the checkbox its name as text
  and the form row carried it as the label too, so every such parameter
  read "write forever [ ] write forever".

## [0.12.3] - 13-09-2026

### Added

- `BufferHandler` and `log_buffer()` (`redsun.log`) - the session's log records,
  retained as they are emitted. The handler is installed on the `redsun` logger
  alongside the stdout one and keeps the most recent 10 000 records, so a
  consumer built later in the session can still show what happened before it
  existed. `BufferHandler.capacity` is how many records it keeps.
- `LogView` (`redsun.view.qt.builtins`) - a read-only console showing those
  records, colour-coded by level in one of two sets chosen from the console's
  own background, so the text keeps its contrast under a light and a dark
  palette alike, and redrawn when the palette changes. Buttons choose the lowest level displayed,
  redrawing from the buffer so raising the threshold never discards anything,
  and `Save logs...` writes every record of the run regardless of what is on
  screen, copied from the session's log file when one is open and taken from
  the buffer otherwise. `Open log folder` opens the folder holding the
  session's log files, and is disabled when no log file is open. Records arriving while it is open are drawn in batches every 100 ms,
  at most 2 000 per batch, and the console keeps no more lines than the buffer
  holds records. Available from a configuration file as `plugin_name: redsun`,
  `plugin_id: logs` under `views`.
- `SessionFileHandler` and `session_log()` (`redsun.log`) - a file of each run's
  log records, at `<user log directory>/redsun/<session>/<start time>_<pid>.log`.
  The file is rotated at 10 MB with 5 older files kept, and opening one deletes
  the files of all but the 20 most recent runs of that session. `session_log()`
  returns the handler installed on the `redsun` logger, or `None`.
- `AppContainer` (`redsun.containers`) opens a `SessionFileHandler` for its
  session when it is constructed and when it is built after a shutdown, and
  `shutdown()` closes it.

### Changed

- **`RunEngine`** (`redsun.engine`) runs each plan, and each `resume`, on a
  thread of its own named `RunEngine`, which ends with the plan, instead of on
  a thread pool kept for the engine's lifetime. A plan submitted while another
  is running fails with `bluesky`'s error instead of waiting its turn.

### Fixed

- **`RunEngine`** (`redsun.engine`) takes `loop=None` and falls back to the
  shared background loop when an engine is built, so importing `redsun.engine`
  no longer starts the loop and its thread.
- **`GlobalFormatter.format`** (`redsun.log`) appends the traceback of a record
  carrying one, and the stack of a record logged with `stack_info=True`, so a
  `logger.exception(...)` call reaches stdout and `LogView` with both.

### Removed

- **`redsun.common.qt.ask_file_path`** and the `redsun.common` package.
- **`QtAppContainer`**'s main window no longer has a `File` menu or its
  `Save configuration as...` action, which wrote no file.

## [0.12.2] - 07-09-2026

### Fixed

- **`QtAppContainer.shutdown`** (`redsun.containers.qt`) stops the timer
  draining `psygnal`'s emission queue and delivers what is left in it before
  destroying the widgets. An emission queued for a slot with a thread affinity
  reached a destroyed widget as `RuntimeError: wrapped C/C++ object of type
  <widget> has been deleted`, and carried into the next container built in the
  same process.

## [0.12.1] - 03-09-2026

### Added

- **`ComponentNotBuilt`** (`redsun.virtual`) - the `WiringError`
  `VirtualContainer.connect_paths` raises for a port path naming a component
  that is not there. It carries the name as `component`.

### Changed

- **`AppContainer.build`** (`redsun.containers.container`) logs a presenter or
  a view that fails to build and carries on, as it already did for a device.
  The build returns, and the component is absent from `presenters` or `views`.

- **`AppContainer.connect`** (`redsun.containers.container`) returns
  `Connection | None`. Either end belonging to a component that failed to
  build is logged at `WARNING` and connects nothing, so the rest of `wire`
  runs. A `declare_*` attribute of such a component reads back as a stand-in
  for the length of that build, and naming a port a *built* component does not
  have still raises `AttributeError`.

- The line closing a build counts what was built against what was declared,
  and names what is missing. It is logged at `WARNING` rather than `INFO` when
  anything failed to build:

  ```
  Container built: 3/4 devices, 2/2 presenters, 4/5 views
  Not built: bad_camera (device), log_panel (view)
  ```

- A `wiring` rule naming a component that failed to build is logged at
  `WARNING` and skipped, and the rules around it connect. A rule naming a
  component that was never declared, one naming a port a built component does
  not expose, a signature mismatch and a malformed rule all still raise.

- **`AppContainer.shutdown`** (`redsun.containers.container`) releases every
  device, presenter and view the container built. `devices`, `presenters` and
  `views` raise until the next `build()`, and a `declare_*` attribute read on a
  shut-down container gives the declaration rather than the built object. Take
  a reference before the shutdown to keep using a component:

  ```python
  app = MyApp().build()
  ctrl = app.ctrl
  app.shutdown()
  ctrl.stop()
  ```

- **`AppContainer.shutdown`** runs as named phases, each overridable by a
  subclass: `_disconnect`, `_shutdown_presenters`, `_shutdown_hooks`,
  `_release_components` and `_destroy`. `_destroy` takes what
  `_release_components` returned and does nothing by default; a toolkit
  overrides it to end objects that releasing does not end.

- **`QtAppContainer`** (`redsun.qt`) closes and destroys the widgets the
  container built and the main window, rather than only releasing them. A view
  read before the shutdown is left wrapping a destroyed widget and raises
  `RuntimeError` on use; presenters are unaffected.

- **`AppContainer`** builds its own components even when another container of
  the same class was built before it. The two no longer share instances.

### Fixed

- **`AppContainer.devices`**, **`AppContainer.presenters`** and
  **`AppContainer.views`** (`redsun.containers.container`) return the
  components the container built. A device whose build failed is absent from
  `devices`, where reading the mapping raised `RuntimeError` before:

  ```python
  class App(AppContainer):
      ok = declare_device(MyMotor, egu="mm")
      bad = declare_device(BrokenMotor)


  set(App().build().devices)  # {"ok"}
  ```

- A wiring report could name a component after a different, released one.
  **`VirtualContainer`** (`redsun.virtual`) resolves component names by
  identity rather than by `id()`, and forgets the built components at shutdown.

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
  reporter instead. It was the only `psygnal` `Signal` on `AppContainer`, so
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
  owning a `psygnal` `Signal`.

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
  link. A slot that is not marked, or whose signature `psygnal` rejects, raises
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
  an `ophyd-async` device signal from a marked slot. The reading is marshalled
  through `psygnal`, so `thread` behaves as it does for `connect`, and the
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
- `redsun.aio.set_async_backend()` - installs `CulsansAsyncioBackend` as `psygnal`'s
  active async backend, so coroutines connected to a signal are dispatched onto the
  shared event loop from any thread. Idempotent; raises if a different backend is
  already active. Tear it down with `psygnal`'s `clear_async_backend()`.
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
- `AppContainer.connect_devices(mock=False)` - connects all registered `ophyd-async` devices
  via their async connect lifecycle. Call after `build()`. Pass `mock=True` to skip hardware
  communication in tests.
- `FrameSink`, `StoreStateError`, and the process-wide storage registry
  (`register_storage`, `get_storage`, `reset_group`, `clear_registry`).
- `culsans` (>=0.11.0) as a runtime dependency.
- `redsun.presenter.builtins` - built-in, reusable presenter components.
  First entry: `StoragePresenter` (ported from redsun-mimir's
  `FileStoragePresenter`), which owns the `SessionPathProvider`, exposes it
  on the virtual container as the `path_provider` DI provider, and wires
  plan names from `sig_pre_launch_notify`/`sig_plan_done`.
- `redsun.plugins` entry point: `redsun` ships its own plugin manifest
  (`plugins.yaml`), so built-in components resolve from configuration files
  through the same discovery path as external plugins
  (`plugin_name: redsun`, `plugin_id: storage`).
- `BaseStorage.path_provider` read-only property.
- `find_signals` accepts an optional `owner` keyword to scope the lookup to
  one component's signal cache (ADR 0004).
- `SinkFactory`, `StorageIO`, `OpenStore`, and `PathSignals` are exported from
  `redsun.storage` - the backend protocols are part of the public contract.
- `benchmarks/` - `acquire-zarr` dual-load benchmark (live view via
  `bps.monitor` + disk storage, two detectors, inline processing callback).
  Shipped in the sdist only, never in wheels, not collected by `pytest`.
- The tutorial on writing a custom storage backend.

### Changed (breaking)

- `redsun.storage` rewritten per ADR 0002: `BaseStorage.sink()` returns a
  `FrameSink` (culsans-backed) usable from async device logics and sync
  document callbacks; `open()`/`close()` are explicit and idempotent.
- Removed `StorageStateMachine`, `StorageState`, `InvalidStoreState`, and the
  `FrameSender` async-generator API. `StoreStateError` replaces
  `InvalidStoreState`.
- Removed `redsun.device.DeviceMap` - `ophyd-async` now ships `DeviceMap` as a
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

- **Custom device layer removed**, `redsun.device` now re-exports `ophyd-async` primitives
  directly. Removed: `PDevice`, `HasChildren`, `AttrR`, `AttrRW`, `AttrW`, `AttrT`,
  `SoftAttrR`, `SoftAttrRW`, `SoftAttrT`, `AcquisitionController`, `DataWriter`,
  `ControllableDataWriter`, `TriggerType`, `PrepareInfo`. Use their `ophyd-async` equivalents
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
  green tests once more. CI `mypy` now uses the config-driven invocation (tests
  and benchmarks in scope) with `QT_API` pinning the Qt binding per matrix
  leg, and `ruff` checks the whole repository instead of `src/redsun` only.

### Removed
- Removed `attrs` from dev dependencies - drop support for it in favor of `ophyd-async`.
- Removed unused utilities: `redsun.utils.resolve_sync_or_async` and
  `redsun.utils.descriptors.make_key` / `make_descriptor` / `make_reading` - descriptors and readings come from `ophyd-async` signal backends; the
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

- Migrated `sunflare` codebase to `redsun`. `sunflare` will be archived.

## [0.7.2] - 22-02-2026

### Changed

- Merged SDK (formerly `sunflare`) into `redsun`
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
  `type[View]`. This fixes `mypy` errors for classes built from protocol mixins that do
  not inherit from the `sunflare` base classes directly.

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
- Bumped `sunflare` version to ```sunflare`>=0.5.0``, which implements the above changes at toolkit level

## [0.1.0] - 22-02-2025

### Added

- Initial release on PyPI

[0.12.3]: https://github.com/redsun-acquisition/redsun/compare/v0.12.2...v0.12.3
[0.12.2]: https://github.com/redsun-acquisition/redsun/compare/v0.12.1...v0.12.2
[0.12.1]: https://github.com/redsun-acquisition/redsun/compare/v0.12.0...v0.12.1
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
