# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Dates are specified in the format `DD-MM-YYYY`.

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

[0.5.6]: https://github.com/redsun-acquisition/redsun/compare/v0.5.5...v0.5.6
[0.5.5]: https://github.com/redsun-acquisition/redsun/compare/v0.5.4...v0.5.5
[0.5.4]: https://github.com/redsun-acquisition/redsun/compare/v0.5.3...v0.5.4
[0.5.3]: https://github.com/redsun-acquisition/redsun/compare/v0.5.2...v0.5.3
[0.5.0]: https://github.com/redsun-acquisition/redsun/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/redsun-acquisition/redsun/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/redsun-acquisition/redsun/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/redsun-acquisition/redsun/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/redsun-acquisition/redsun/compare/v0.1.0
