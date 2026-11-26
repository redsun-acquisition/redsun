"""Tests for the reports the `redsun` command prints."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from redsun._reports import FORMAT, CheckReport, Component, report_schemas

SCHEMAS = Path(__file__).parent.parent.parent / "schemas"


@pytest.mark.parametrize("name", sorted(report_schemas()))
def test_the_committed_schema_is_the_one_the_models_produce(name: str) -> None:
    """Fail when a report's model changed and its committed schema did not."""
    committed = json.loads((SCHEMAS / f"{name}.schema.json").read_text("utf-8"))

    assert committed == report_schemas()[name], (
        "regenerate it with `uv run python scripts/export_schemas.py`"
    )


def test_a_check_report_prints_a_component_s_class_under_the_key_class() -> None:
    """Print a component's class path under `class`, as the session file writes it."""
    report = CheckReport(
        redsun="0",
        format=FORMAT,
        problems=[],
        components=[
            Component.model_validate(
                {
                    "name": "stage",
                    "group": "devices",
                    "plugin_name": "mylab",
                    "plugin_id": "motor",
                    "class": "mylab.devices:MyMotor",
                    "status": "passed",
                }
            )
        ],
        lookups=[],
        skipped=[],
    )

    assert '"class": "mylab.devices:MyMotor"' in report.to_json()
