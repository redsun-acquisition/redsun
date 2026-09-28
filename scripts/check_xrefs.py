"""Fail if the built documentation contains syntax the build left unread.

``zensical build`` reports "No issues found" even when a ``[`Name`][target]``
reference matched nothing, when a snippet marker is misspelt, or when a link
names a part of a page that does not exist. The first two are emitted verbatim
into the page and the third leads to the top of it. This script scans the
built site for all three.
"""

from __future__ import annotations

import html
import re
import sys
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import unquote, urlsplit

if TYPE_CHECKING:
    from collections.abc import Iterator

SITE = Path(__file__).resolve().parent.parent / "site"

# a rendered docstring is printed a second time inside the source block, and a
# reference written in a code span is documentation about the syntax itself
LITERAL = re.compile(r"<pre\b.*?</pre>|<code\b.*?</code>", re.DOTALL)
UNRESOLVED = re.compile(r"\]\[([^\]\s<]*)\]")
TAG = re.compile(r"<[^>]+>")
# a formatter reading the marker as Python spaces it out, so allow for that
SNIPPET = re.compile(r"^\s*-\s*-\s*8\s*<\s*-\s*-.*$", re.MULTILINE)

HREF = re.compile(r'<a\b[^>]*?\bhref="([^"]+)"')
ID = re.compile(r'\bid="([^"]+)"')


@cache
def ids(page: Path) -> frozenset[str]:
    """Return the ``id`` of every element of *page*."""
    return frozenset(ID.findall(page.read_text(encoding="utf-8")))


def dangling(site: Path) -> Iterator[str]:
    """Yield a line for each link of *site* whose fragment reaches nothing.

    Links to another site are left alone, and so are fragments starting with
    two underscores, which the theme handles in the browser.
    """
    for page in sorted(site.rglob("*.html")):
        for href in sorted(set(HREF.findall(page.read_text(encoding="utf-8")))):
            parts = urlsplit(html.unescape(href))
            fragment = unquote(parts.fragment)
            if parts.scheme or parts.netloc or not fragment:
                continue
            if fragment.startswith("__"):
                continue
            target = page.parent / unquote(parts.path) if parts.path else page
            if target.is_dir():
                target = target / "index.html"
            if target.is_file() and fragment not in ids(target):
                yield (
                    f"{page.relative_to(site).as_posix()}: no #{fragment} in "
                    f"{target.resolve().relative_to(site.resolve()).as_posix()}"
                )


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

    for line in dangling(SITE):
        print(line)
        found += 1

    if found:
        print(f"\n{found} unresolved cross-reference(s), snippet(s) or link(s)")
        return 1
    print("no unresolved cross-references, snippets or links")
    return 0


if __name__ == "__main__":
    sys.exit(main())
