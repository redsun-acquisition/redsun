# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Dates are specified in the format `DD-MM-YYYY`.

## [Unreleased]

### Added

- `SoftAttr` — public base class for `SoftAttrR`, `SoftAttrRW`, and `SoftAttrT`,
  providing the shared `name` property and `set_name()` method.
- `Device.children()` — iterate over registered child devices as `(attr_name, device)` pairs.
- `Device.set_name(name)` — update a device's name and propagate recursively to child
  devices and `SoftAttr*` fields.
- `SoftAttrR.set_name()` / `SoftAttrT.set_name()` (via `SoftAttr`) — called automatically
  by the parent device on attribute assignment.
- `PDevice.set_name()` — added to the minimal device protocol; structurally compatible with
  `ophyd_async.core.Device`.

### Changed

- **`SoftAttrR`, `SoftAttrRW`, `SoftAttrT` constructor signatures changed (breaking).**
  `initial_value` (or `action` for `SoftAttrT`) is now the first positional argument;
  `name` is now keyword-only with a default of `""`.

  ```python
  # Before
  SoftAttrRW[float](f"{name}-position", 0.0, units="mm")

  # After — inside a Device (name auto-injected on assignment)
  SoftAttrRW[float](0.0, units="mm")

  # After — standalone use
  SoftAttrRW[float](0.0, name="stage-position", units="mm")
  ```

- **attrs-decorated `Device` subclasses must add `on_setattr=setters.NO_OP` (breaking).**
  Without it, attrs generates a `__setattr__` on the subclass that shadows
  `Device.__setattr__`, silently skipping child registration and name injection.
- `Device.parent` now returns the actual parent `Device` (or `None` for root devices)
  instead of always `None`.

- `AttrR[T]`, `AttrRW[T]`, `AttrW[T]`, `AttrT` structural protocols mirroring ophyd-async
  `SignalR` / `SignalRW` / `SignalW` / `SignalX` via the same bluesky protocols
  (`Readable`, `Subscribable`, `Movable`, `Triggerable`).
- `SoftAttrR[T]`, `SoftAttrRW[T]`, `SoftAttrT` — in-memory concrete implementations of
  the above, intended for simulation devices and test fixtures.
- `AcquisitionController` protocol: hardware-side acquisition logic (arm, disarm, prepare,
  wait); mirrors `ophyd_async.core.DetectorController`.
- `DataWriter` protocol: persistence-side acquisition logic for a single device (open,
  close, collect stream docs); mirrors `ophyd_async.core.DetectorWriter`.
  `ControllableDataWriter` extends it further with `register()`, `write_frame()`, and
  `set_uri()` for shared multi-source backends.
- `FlyerController[T]` protocol: motion and trigger sequencing for fly scans; mirrors
  `ophyd_async.core.FlyerController`.
- `TriggerInfo` protocol and `TriggerType` enum: trigger configuration passed to devices
  at prepare time; mirror their ophyd-async equivalents.
- `PrepareInfo` dataclass: plan-time information (`capacity`, `write_forever`) passed to
  device `prepare()` methods.
- `Writer.update_metadata(metadata)`: accumulates a `dict` of metadata entries written into
  the backend at `open()` time.
- `Writer.clear_metadata()`: resets accumulated metadata; called automatically by
  `Writer.close()` so each run starts clean.
- `HasWriterLogic` protocol: structural check for devices that expose a `writer_logic`
  property; replaces the removed `HasWriter`.
- `HasMetadata` protocol: structural check for writers that implement `update_metadata()`
  and `clear_metadata()`.
- `handle_descriptor_metadata(doc, devices)`: standalone helper for bluesky callbacks that
  forwards descriptor configuration into associated writers via `HasWriterLogic` and
  `HasMetadata`.

### Changed

- `Writer` now formally inherits `ControllableDataWriter`.
- `get_available_writers()` now takes a `devices: Mapping[str, Any]` argument and discovers
  unique `Writer` instances via `HasWriterLogic`, replacing the removed class-level registry.
- Metadata lifecycle moved from a global module-level registry to per-instance accumulation:
  devices call `writer.update_metadata()` in `prepare()`; metadata is cleared on
  `Writer.close()`.
- `AppContainerMeta` metaclass replaced with `__init_subclass__` for container subclass
  registration.
- Dropped `beartype` as a runtime dependency.
- Bumped `acquire-zarr`.
- Updated CI tag pattern to support release candidates (e.g. `v0.10.0rc0`).

### Removed

- `HasWriter` protocol — replaced by `HasWriterLogic`.
- `Writer.get()` and `Writer.release()` class methods and the underlying `Writer._registry`
  singleton: writers are now created once by the application and injected into devices at
  construction time.
- `storage/metadata.py` and its `register_metadata` / `clear_metadata` / `snapshot_metadata`
  functions — superseded by `Writer.update_metadata()` and `Writer.clear_metadata()`.
- `storage/device.py` and its `make_writer()` factory shim — writers are now provided via
  dependency injection.

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
