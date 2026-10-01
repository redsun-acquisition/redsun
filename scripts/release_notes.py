"""Write a release's changelog section from GitHub's generated release notes.

`prepare VERSION` asks GitHub for the notes of the pull requests merged since
the last final release, turns them into a Keep a Changelog section, and writes
it with its compare link into `docs/reference/changelog.md`.
`extract VERSION` prints that section's body, for the GitHub release.

Both run from the repository root; `prepare` also needs the `gh` command,
logged in.
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
    r"^\* (?P<title>.+?) by @(?P<author>\S+) "
    r"in (?P<url>https://\S+/pull/(?P<number>\d+))$"
)
LINK = re.compile(r"^\[[^\]]+\]: https?://")
TYPE = re.compile(r"^[a-z]+(\([^)]*\))?!?:\s*")
FINAL_TAG = re.compile(r"^v\d+\.\d+\.\d+$")
VERSION = re.compile(r"\d+\.\d+\.\d+")


def gh(*args: str) -> str:
    """Run `gh` and return what it prints."""
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


def worded(title: str) -> str:
    """Return *title* as a changelog entry words it.

    Without the type and scope a commit's first line starts with, which the
    heading of the section already says, and starting with a capital.
    """
    summary = TYPE.sub("", title, count=1)
    return summary[:1].upper() + summary[1:]


def credited(author: str) -> str:
    """Return a link to *author*'s GitHub profile, as GitHub names them in notes.

    A bot, such as `dependabot[bot]`, has its profile under `apps/`.
    """
    if author.endswith("[bot]"):
        name = author.removesuffix("[bot]")
        return f"[@{name}](https://github.com/apps/{name})"
    return f"[@{author}](https://github.com/{author})"


def section(version: str, date: datetime.date, notes: str, breaking: set[int]) -> str:
    """Return the changelog section for *version* from GitHub's *notes*.

    Headings and entries are kept; an entry becomes its pull request's title,
    as `worded`, its link and its author's, as `credited`, marked as breaking
    when its number is in *breaking*. The new contributors block and the
    compare link GitHub adds are dropped.
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
            title = worded(match["title"])
            author = credited(match["author"])
            lines.append(f"- {marker}{title} ([#{number}]({match['url']})) by {author}")
    return "\n".join(lines) + "\n"


def insert(changelog: str, new_section: str, link: str) -> str:
    """Return *changelog* with *new_section* above the newest and *link* at the end."""
    first = changelog.find("\n## [")
    if first == -1:
        return f"{changelog.rstrip()}\n\n{new_section}\n{link}\n"
    head, rest = changelog[:first].rstrip(), changelog[first + 1 :].rstrip()
    return f"{head}\n\n{new_section}\n{rest}\n{link}\n"


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
            f"run `uv run python scripts/release_notes.py prepare {version}` first"
        )
    start = changelog.index(heading)
    body_start = changelog.index("\n", start) + 1
    end = changelog.find("\n## [", body_start)
    body = changelog[body_start:] if end == -1 else changelog[body_start:end]
    kept = [line for line in body.splitlines() if not LINK.match(line)]
    return "\n".join(kept).strip() + "\n"


def prepare(version: str) -> None:
    """Write *version*'s section and compare link into the changelog.

    Raises
    ------
    ValueError
        When *version* is not three dot-separated numbers, such as `0.14.0`,
        or the changelog already has a section for it.
    """
    if not VERSION.fullmatch(version):
        raise ValueError(f"version must look like 0.14.0, got {version!r}")
    if f"## [{version}]" in CHANGELOG.read_text(encoding="utf-8"):
        raise ValueError(
            f"the changelog already has a section for {version}; "
            "discard it with `git checkout docs/reference/changelog.md` first"
        )
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
    """Run `prepare` or `extract` for the version given."""
    command, version = sys.argv[1], sys.argv[2]
    try:
        if command == "prepare":
            prepare(version)
        elif command == "extract":
            sys.stdout.write(extract(CHANGELOG.read_text(encoding="utf-8"), version))
        else:
            sys.exit(f"unknown command {command!r}; expected 'prepare' or 'extract'")
    except (LookupError, ValueError) as error:
        sys.exit(str(error))


if __name__ == "__main__":
    main()
