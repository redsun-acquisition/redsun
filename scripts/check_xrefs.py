"""Fail if the built documentation contains syntax the build left unread.

``zensical build`` reports "No issues found" even when a ``[`Name`][target]``
reference matched nothing, or when a snippet marker is misspelt: either is
emitted verbatim into the page. This script scans the built site for both.
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"

# a rendered docstring is printed a second time inside the source block, and a
# reference written in a code span is documentation about the syntax itself
LITERAL = re.compile(r"<pre\b.*?</pre>|<code\b.*?</code>", re.DOTALL)
UNRESOLVED = re.compile(r"\]\[([^\]\s<]*)\]")
TAG = re.compile(r"<[^>]+>")
# a formatter reading the marker as Python spaces it out, so allow for that
SNIPPET = re.compile(r"^\s*-\s*-\s*8\s*<\s*-\s*-.*$", re.MULTILINE)


def main() -> int:
    """Report every unresolved reference or snippet and return the exit status."""
    if not SITE.is_dir():
        print(f"{SITE} does not exist; run `uv run --group docs zensical build` first")
        return 1

    found = 0
    for page in sorted(SITE.rglob("*.html")):
        text = page.read_text(encoding="utf-8")
        name = page.relative_to(SITE).as_posix()
        for match in UNRESOLVED.finditer(LITERAL.sub("", text)):
            print(f"{name}: unresolved [{match.group(1)}]")
            found += 1
        for match in SNIPPET.finditer(html.unescape(TAG.sub("", text))):
            print(f"{name}: snippet not included: {match.group().strip()}")
            found += 1

    if found:
        print(f"\n{found} unresolved cross-reference(s) or snippet(s)")
        return 1
    print("no unresolved cross-references or snippets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
