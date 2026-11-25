"""Write the JSON schemas of a session file, a plugin manifest and the command reports.

The first two land in `docs/reference/schemas/`, which the docs build
publishes, so an editor can check a file against them while it is written.
Those of the reports land in `schemas/`, which is committed: a program
reading a report takes its types from there, and a test fails when a file no
longer matches its model.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from redsun._config import session_file_schema
from redsun._manifest import PluginManifest
from redsun._reports import report_schemas

ROOT = Path(__file__).parent.parent
TARGET = ROOT / "docs" / "reference" / "schemas"
REPORTS = ROOT / "schemas"


def write(path: Path, schema: dict[str, Any]) -> None:
    """Write *schema* to *path* as indented JSON."""
    path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path}")


def main() -> None:
    """Write one schema file per file kind and per report."""
    TARGET.mkdir(parents=True, exist_ok=True)
    for name, schema in (
        ("session-file", session_file_schema()),
        ("plugin-manifest", PluginManifest.model_json_schema()),
    ):
        write(TARGET / f"{name}.schema.json", schema)
    REPORTS.mkdir(exist_ok=True)
    for name, schema in report_schemas().items():
        write(REPORTS / f"{name}.schema.json", schema)


if __name__ == "__main__":
    main()
