"""Links of a built site whose fragment reaches no element."""

from __future__ import annotations

from pathlib import Path

from scripts.check_xrefs import dangling


def page(site: Path, address: str, body: str) -> None:
    target = site / address / "index.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"<html><body>{body}</body></html>", encoding="utf-8")


def test_a_fragment_reaching_nothing_is_reported(tmp_path: Path) -> None:
    page(tmp_path, "glossary", '<h3 id="device">Device</h3>')
    page(
        tmp_path,
        "guide",
        '<a href="../glossary/#device">device</a>'
        '<a href="../glossary/#devise">misspelt</a>'
        '<a href="#nowhere">same page</a>'
        '<a href="https://example.org/#elsewhere">outside</a>'
        '<a href="#__skip">theme</a>',
    )

    found = sorted(dangling(tmp_path))

    assert found == [
        "guide/index.html: no #devise in glossary/index.html",
        "guide/index.html: no #nowhere in guide/index.html",
    ]
