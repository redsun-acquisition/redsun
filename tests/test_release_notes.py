"""The notes a GitHub release takes from its changelog section."""

from __future__ import annotations

import pytest

from scripts.release_notes import extract

CHANGELOG = """\
# Changelog

Intro.

<!-- towncrier release notes start -->

## [0.15.0](https://github.com/o/r/releases/tag/v0.15.0) - 12-10-2026

### Breaking

- Drop a hook ([#141](https://github.com/o/r/pull/141))

### Added

- Add strict sessions ([#140](https://github.com/o/r/pull/140))

## [0.14.3] - 01-10-2026

### Added

- an older addition

[0.14.3]: https://github.com/o/r/compare/v0.14.2...v0.14.3
"""


def test_a_section_towncrier_wrote_is_read_back() -> None:
    """Read a section under a linked heading, and an older one, each without its heading or links."""
    assert extract(CHANGELOG, "0.15.0") == (
        "### Breaking\n\n- Drop a hook ([#141](https://github.com/o/r/pull/141))\n\n"
        "### Added\n\n- Add strict sessions ([#140](https://github.com/o/r/pull/140))\n"
    )
    assert extract(CHANGELOG, "0.14.3") == "### Added\n\n- an older addition\n"


def test_reading_a_version_never_built_names_the_build_command() -> None:
    """Refuse a missing section with a message naming the command that writes it."""
    with pytest.raises(LookupError, match=r"towncrier build --version 0\.16\.0"):
        extract(CHANGELOG, "0.16.0")
