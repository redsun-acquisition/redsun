"""The keys the reference lists against the keys a file can hold."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from redsun._config import session_file_schema
from redsun._manifest import PluginManifest

REFERENCE = Path(__file__).parent.parent / "docs" / "reference"
FIRST_CELL = re.compile(r"^\| `([\w.]+)` \|", re.MULTILINE)


def keys_of(schema: dict[str, Any]) -> set[str]:
    """Return the top-level keys of *schema*, and those of what it defines."""
    found = set(schema.get("properties", {}))
    for definition in schema.get("$defs", {}).values():
        found |= set(definition.get("properties", {}))
    return found


@pytest.mark.parametrize(
    ("page", "schema"),
    [
        ("session-file.md", session_file_schema()),
        ("plugin-manifest.md", PluginManifest.model_json_schema()),
    ],
)
def test_the_page_lists_every_key_of_the_file(
    page: str, schema: dict[str, Any]
) -> None:
    text = (REFERENCE / page).read_text(encoding="utf-8")
    listed = {cell.rpartition(".")[2] for cell in FIRST_CELL.findall(text)}

    assert keys_of(schema) <= listed
