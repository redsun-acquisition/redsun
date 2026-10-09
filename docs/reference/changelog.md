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
