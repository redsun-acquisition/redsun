"""Write a release's changelog section from GitHub's generated release notes.

``prepare VERSION`` asks GitHub for the notes of the pull requests merged since
the last final release, turns them into a Keep a Changelog section, and writes
it with its compare link into ``docs/reference/changelog.md``.
``extract VERSION`` prints that section's body, for the GitHub release.

Both need the ``gh`` command, logged in, and run from the repository root.
"""

from __future__ import annotations

import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

CHANGELOG = Path("docs/reference/changelog.md")
REPOSITORY = "redsun-acquisition/redsun"
ENTRY = re.compile(
    r"^\* (?P<title>.+?) by @\S+ in (?P<url>https://\S+/pull/(?P<number>\d+))$"
)
LINK = re.compile(r"^\[[^\]]+\]: https?://")
FINAL_TAG = re.compile(r"^v\d+\.\d+\.\d+$")


def gh(*args: str) -> str:
    """Run ``gh`` and return what it prints."""
    return subprocess.run(
        ["gh", *args], check=True, capture_output=True, text=True
    ).stdout


def previous_final_tag() -> str:
    """Return the newest tag naming a final release, not a release candidate."""
    tags = subprocess.run(
        ["git", "tag", "--list", "v*", "--sort=-v:refname"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    return next(tag for tag in tags if FINAL_TAG.match(tag))


def entries(notes: str) -> list[re.Match[str]]:
    """Return the pull request lines of GitHub's *notes*."""
    return [m for line in notes.splitlines() if (m := ENTRY.match(line.strip()))]


def section(version: str, date: datetime.date, notes: str, breaking: set[int]) -> str:
    """Return the changelog section for *version* from GitHub's *notes*.

    Headings and entries are kept; an entry becomes its pull request's title
    and link, marked as breaking when its number is in *breaking*. The
    contributor lines and the compare link GitHub adds are dropped.
    """
    lines = [f"## [{version}] - {date:%d-%m-%Y}"]
    for raw in notes.splitlines():
        line = raw.strip()
        if line.startswith("## New Contributors"):
            break
        if line.startswith("### "):
            lines += ["", line, ""]
            continue
        match = ENTRY.match(line)
        if match is not None:
            number = int(match["number"])
            marker = "**Breaking:** " if number in breaking else ""
            lines.append(f"- {marker}{match['title']} ([#{number}]({match['url']}))")
    return "\n".join(lines) + "\n"


def insert(changelog: str, new_section: str, link: str) -> str:
    """Return *changelog* with *new_section* above the newest and *link* at the end."""
    first = changelog.find("\n## [")
    if first == -1:
        return f"{changelog.rstrip()}\n\n{new_section}\n{link}\n"
    head, rest = changelog[:first].rstrip(), changelog[first + 1 :].rstrip()
    return f"{head}\n\n{new_section}\n{rest}\n{link}\n"


def extract(changelog: str, version: str) -> str:
    """Return the body of *version*'s section in *changelog*, without its heading."""
    start = changelog.index(f"## [{version}]")
    body_start = changelog.index("\n", start) + 1
    end = changelog.find("\n## [", body_start)
    body = changelog[body_start:] if end == -1 else changelog[body_start:end]
    kept = [line for line in body.splitlines() if not LINK.match(line)]
    return "\n".join(kept).strip() + "\n"


def prepare(version: str) -> None:
    """Write *version*'s section and compare link into the changelog."""
    previous = previous_final_tag()
    notes: str = json.loads(
        gh(
            "api",
            f"repos/{REPOSITORY}/releases/generate-notes",
            "-f",
            f"tag_name=v{version}",
            "-f",
            f"previous_tag_name={previous}",
        )
    )["body"]
    breaking = {
        number
        for number in {int(match["number"]) for match in entries(notes)}
        if "breaking"
        in json.loads(
            gh(
                "pr",
                "view",
                str(number),
                "--json",
                "labels",
                "--jq",
                "[.labels[].name]",
            )
        )
    }
    today = datetime.datetime.now(datetime.UTC).date()
    new_section = section(version, today, notes, breaking)
    link = (
        f"[{version}]: https://github.com/{REPOSITORY}/compare/{previous}...v{version}"
    )
    CHANGELOG.write_text(
        insert(CHANGELOG.read_text(encoding="utf-8"), new_section, link),
        encoding="utf-8",
        newline="\n",
    )


def main() -> None:
    """Run ``prepare`` or ``extract`` for the version given."""
    command, version = sys.argv[1], sys.argv[2]
    if command == "prepare":
        prepare(version)
    elif command == "extract":
        sys.stdout.write(extract(CHANGELOG.read_text(encoding="utf-8"), version))
    else:
        sys.exit(f"unknown command {command!r}; expected 'prepare' or 'extract'")


if __name__ == "__main__":
    main()
