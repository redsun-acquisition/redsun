"""The extras the installation page offers against the ones the package declares."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).parent.parent
NOT_OFFERED = {"qt-common"}
EXTRA_ROW = re.compile(r'data-role="extra".*?</div>', re.DOTALL)
VALUE = re.compile(r'data-value="([^"]+)"')


def test_the_page_offers_the_extras_the_package_declares() -> None:
    """Offer on the installation page exactly the extras the package declares."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    declared = set(project["project"]["optional-dependencies"]) - NOT_OFFERED
    page = (ROOT / "docs/how-to/install-redsun.md").read_text(encoding="utf-8")
    offered = {value for row in EXTRA_ROW.findall(page) for value in VALUE.findall(row)}

    assert offered == declared
