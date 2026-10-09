"""Print a release's changelog section, for the GitHub release.

`extract VERSION` prints the body of that version's section in
`docs/reference/changelog.md`, without its heading or compare links. Run it
from the repository root.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

CHANGELOG = Path("docs/reference/changelog.md")
LINK = re.compile(r"^\[[^\]]+\]: https?://")


def extract(changelog: str, version: str) -> str:
    """Return the body of *version*'s section in *changelog*, without its heading.

    Raises
    ------
    LookupError
        When *changelog* has no section for *version*.
    """
    heading = f"## [{version}]"
    if heading not in changelog:
        raise LookupError(
            f"the changelog has no section for {version}; "
            f"run `uv run towncrier build --version {version}` first"
        )
    start = changelog.index(heading)
    body_start = changelog.index("\n", start) + 1
    end = changelog.find("\n## [", body_start)
    body = changelog[body_start:] if end == -1 else changelog[body_start:end]
    kept = [line for line in body.splitlines() if not LINK.match(line)]
    return "\n".join(kept).strip() + "\n"


def main() -> None:
    """Print the section of the version given, or exit naming what is missing."""
    command, version = sys.argv[1], sys.argv[2]
    if command != "extract":
        sys.exit(f"unknown command {command!r}; expected 'extract'")
    try:
        sys.stdout.write(extract(CHANGELOG.read_text(encoding="utf-8"), version))
    except LookupError as error:
        sys.exit(str(error))


if __name__ == "__main__":
    main()
