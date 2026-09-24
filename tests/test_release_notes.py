"""The changelog section a release is prepared with, and the notes read back from it."""

from __future__ import annotations

import datetime

from scripts.release_notes import extract, insert, section

NOTES = """\
## What's Changed
### Added
* feat: add strict sessions by @someone in https://github.com/o/r/pull/140
### Changed
* refactor!: promote the session layer by @someone in https://github.com/o/r/pull/141

## New Contributors
* @newcomer made their first contribution in https://github.com/o/r/pull/139

**Full Changelog**: https://github.com/o/r/compare/v0.13.0...v0.14.0
"""

CHANGELOG = """\
# Changelog

Intro.

## [0.13.0] - 23-09-2026

### Fixed

- an older fix

[0.13.0]: https://github.com/o/r/compare/v0.12.0...v0.13.0
"""


def test_a_release_section_is_written_above_the_last_and_read_back() -> None:
    new = section("0.14.0", datetime.date(2026, 10, 1), NOTES, breaking={141})
    link = "[0.14.0]: https://github.com/o/r/compare/v0.13.0...v0.14.0"

    changelog = insert(CHANGELOG, new, link)

    assert (
        changelog
        == """\
# Changelog

Intro.

## [0.14.0] - 01-10-2026

### Added

- feat: add strict sessions ([#140](https://github.com/o/r/pull/140))

### Changed

- **Breaking:** refactor!: promote the session layer ([#141](https://github.com/o/r/pull/141))

## [0.13.0] - 23-09-2026

### Fixed

- an older fix

[0.13.0]: https://github.com/o/r/compare/v0.12.0...v0.13.0
[0.14.0]: https://github.com/o/r/compare/v0.13.0...v0.14.0
"""
    )
    assert extract(changelog, "0.13.0") == "### Fixed\n\n- an older fix\n"
    assert extract(changelog, "0.14.0").startswith("### Added\n")


def test_the_first_section_goes_below_the_introduction() -> None:
    new = section("0.14.0", datetime.date(2026, 10, 1), NOTES, breaking=set())

    changelog = insert("# Changelog\n\nIntro.\n", new, "[0.14.0]: https://x")

    assert changelog.startswith("# Changelog\n\nIntro.\n\n## [0.14.0] - 01-10-2026\n")
    assert changelog.endswith("\n[0.14.0]: https://x\n")
    assert "New Contributors" not in changelog
    assert "Full Changelog" not in changelog
