"""Decide whether a pull request changes documentation alone.

CI runs it from the repository root, with `PR`, `REPO` and `GH_TOKEN` set for
`gh`, and `GITHUB_OUTPUT` naming the file a step writes its outputs to. It
writes `docs_only=true` when the pull request carries the `docs-only` label
and every file it changes is documentation, and `docs_only=false` when the
label is missing or the run is not for a pull request. When the label is set
but a changed file is not documentation, it exits with an error naming the
files.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

LABEL = "docs-only"
CODE_UNDER_DOCS = frozenset({".py", ".yaml", ".yml"})


def is_documentation(path: str) -> bool:
    """Whether the repository file *path* is documentation.

    Documentation is a file under `docs/` other than a script or a session
    file, which the tests import; a file under `changelog.d/`;
    `zensical.toml`; and a Markdown file at the root.
    """
    file = PurePosixPath(path)
    match file.parts:
        case ("docs", _, *_):
            return file.suffix not in CODE_UNDER_DOCS
        case ("changelog.d", _, *_) | ("zensical.toml",):
            return True
        case (_,):
            return file.suffix == ".md"
    return False


def not_documentation(paths: Iterable[str]) -> list[str]:
    """Return the paths among *paths* that are not documentation, in order."""
    return [path for path in paths if not is_documentation(path)]


def gh(*args: str) -> str:
    """Return what the `gh` command with *args* prints."""
    return subprocess.run(
        ["gh", *args], check=True, stdout=subprocess.PIPE, text=True
    ).stdout


def main() -> None:
    """Write `docs_only` for the pull request in `PR`, or exit naming the files that are not documentation."""
    pr, repo = os.environ.get("PR", ""), os.environ.get("REPO", "")
    docs_only = False
    if pr:
        # read now rather than from the event: a label given when the pull
        # request opens arrives a moment after its "opened" event
        labels = json.loads(gh("pr", "view", pr, "--repo", repo, "--json", "labels"))
        if any(label["name"] == LABEL for label in labels["labels"]):
            changed = gh("pr", "diff", pr, "--repo", repo, "--name-only").splitlines()
            other = not_documentation(path for path in changed if path)
            if other:
                print(
                    f"::error::Labelled {LABEL}, but these files are not "
                    f"documentation: {', '.join(other)}. Remove the label or "
                    "move them to another pull request."
                )
                sys.exit(1)
            print(f"Labelled {LABEL} and every changed file is documentation.")
            docs_only = True
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
        output.write(f"docs_only={str(docs_only).lower()}\n")


if __name__ == "__main__":
    main()
