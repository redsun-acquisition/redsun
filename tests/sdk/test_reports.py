"""Tests for the reports the `redsun` command prints."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from redsun._reports import report_schemas

SCHEMAS = Path(__file__).parent.parent.parent / "schemas"


@pytest.mark.parametrize("name", sorted(report_schemas()))
def test_the_committed_schema_is_the_one_the_models_produce(name: str) -> None:
    """Fail when a report's model changed and its committed schema did not."""
    committed = json.loads((SCHEMAS / f"{name}.schema.json").read_text("utf-8"))

    assert committed == report_schemas()[name], (
        "regenerate it with `uv run python scripts/export_schemas.py`"
    )
