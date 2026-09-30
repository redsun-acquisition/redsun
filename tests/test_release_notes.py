"""The changelog section a release is prepared with, and the notes read back from it."""

from __future__ import annotations

import datetime

import pytest

from scripts.release_notes import extract, insert, prepare, section, worded

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
    """Write a release section above the previous one and read both back."""
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

- Add strict sessions ([#140](https://github.com/o/r/pull/140))

### Changed

- **Breaking:** Promote the session layer ([#141](https://github.com/o/r/pull/141))

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
    """Put the first section below the introduction, without contributors or links."""
    new = section("0.14.0", datetime.date(2026, 10, 1), NOTES, breaking=set())

    changelog = insert("# Changelog\n\nIntro.\n", new, "[0.14.0]: https://x")

    assert changelog.startswith("# Changelog\n\nIntro.\n\n## [0.14.0] - 01-10-2026\n")
    assert changelog.endswith("\n[0.14.0]: https://x\n")
    assert "New Contributors" not in changelog
    assert "Full Changelog" not in changelog


@pytest.mark.parametrize(
    ("title", "entry"),
    [
        pytest.param("feat: add strict sessions", "Add strict sessions", id="type"),
        pytest.param("fix(engine): wake a latch", "Wake a latch", id="scope"),
        pytest.param("refactor(qt)!: drop a hook", "Drop a hook", id="breaking"),
        pytest.param(
            "fix: `wire` yields links", "`wire` yields links", id="code-first"
        ),
        pytest.param("Bump the actions group", "Bump the actions group", id="no-type"),
        pytest.param("docs: say why: a colon", "Say why: a colon", id="second-colon"),
    ],
)
def test_an_entry_drops_the_type_its_section_already_says(
    title: str, entry: str
) -> None:
    """Drop the commit type and scope from an entry and capitalise a leading letter."""
    assert worded(title) == entry


def test_reading_a_version_never_prepared_names_the_prepare_command() -> None:
    """Refuse a missing section with a message naming the prepare command."""
    with pytest.raises(LookupError, match=r"release_notes\.py prepare 0\.14\.1"):
        extract(CHANGELOG, "0.14.1")


@pytest.mark.parametrize("version", ["v0.14.1", "0.14", "0.14.1rc1", ""])
def test_preparing_a_version_not_shaped_x_y_z_is_refused(version: str) -> None:
    """Refuse a version that is not three dot-separated numbers."""
    with pytest.raises(ValueError, match="0.14.0"):
        prepare(version)
