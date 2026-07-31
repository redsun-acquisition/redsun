"""Fail if the built documentation contains an unresolved cross-reference.

``zensical build`` reports "No issues found" even when a ``[`Name`][target]``
reference matched nothing: the target is emitted verbatim into the page. This
script scans the built site for that leftover syntax.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"

# a rendered docstring is printed a second time inside the source block, and a
# reference written in a code span is documentation about the syntax itself
LITERAL = re.compile(r"<pre\b.*?</pre>|<code\b.*?</code>", re.DOTALL)
UNRESOLVED = re.compile(r"\]\[([^\]\s<]*)\]")


def main() -> int:
    """Report every unresolved reference and return the exit status."""
    if not SITE.is_dir():
        print(f"{SITE} does not exist; run `uv run zensical build` first")
        return 1

    found = 0
    for page in sorted(SITE.rglob("*.html")):
        prose = LITERAL.sub("", page.read_text(encoding="utf-8"))
        for match in UNRESOLVED.finditer(prose):
            print(f"{page.relative_to(SITE).as_posix()}: unresolved [{match.group(1)}]")
            found += 1

    if found:
        print(f"\n{found} unresolved cross-reference(s)")
        return 1
    print("no unresolved cross-references")
    return 0


if __name__ == "__main__":
    sys.exit(main())
