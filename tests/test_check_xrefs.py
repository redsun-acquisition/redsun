"""Links of a built site whose fragment reaches no element."""

from __future__ import annotations

from pathlib import Path

from scripts.check_xrefs import dangling


def page(site: Path, address: str, body: str) -> None:
    target = site / address / "index.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"<html><body>{body}</body></html>", encoding="utf-8")


def test_a_fragment_reaching_nothing_is_reported(tmp_path: Path) -> None:
    """Report a fragment that names no element, ignoring outside and theme links."""
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


def test_a_link_leaving_the_site_is_reported(tmp_path: Path) -> None:
    """Report a link whose target lies outside the site."""
    site = tmp_path / "site"
    page(site, "guide", '<a href="../../outside/#part">outside</a>')
    outside = tmp_path / "outside" / "index.html"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_text("<html><body></body></html>", encoding="utf-8")

    assert list(dangling(site)) == [
        "guide/index.html: ../../outside/#part leaves the site",
    ]


def test_a_link_to_a_page_that_does_not_exist_is_reported(tmp_path: Path) -> None:
    """Report a link to a page that does not exist."""
    page(tmp_path, "glossary", '<h3 id="device">Device</h3>')
    page(tmp_path, "guide", '<a href="../glosary/#device">misspelt page</a>')

    assert list(dangling(tmp_path)) == [
        "guide/index.html: ../glosary/#device names a page that does not exist"
    ]


def test_an_attribute_ending_in_id_or_href_is_not_read_as_one(tmp_path: Path) -> None:
    """Read only the `id` and `href` attributes, not ones ending in those names."""
    page(tmp_path, "glossary", '<h3 data-id="ghost">Ghost</h3>')
    page(
        tmp_path,
        "guide",
        '<a href="../glossary/#ghost">named by data-id only</a>'
        '<a data-href="../glossary/#nothing" href="../glossary/">no fragment</a>',
    )

    assert list(dangling(tmp_path)) == [
        "guide/index.html: no #ghost in glossary/index.html"
    ]
