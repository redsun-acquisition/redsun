"""Write the JSON schemas of a session file and a plugin manifest.

They land in ``docs/reference/schemas/``, which the docs build publishes, so an
editor can check a file against them while it is written.
"""

from __future__ import annotations

import json
from pathlib import Path

from redsun._config import session_file_schema
from redsun._manifest import PluginManifest

TARGET = Path(__file__).parent.parent / "docs" / "reference" / "schemas"


def main() -> None:
    """Write one schema file per file kind."""
    TARGET.mkdir(parents=True, exist_ok=True)
    for name, schema in (
        ("session-file", session_file_schema()),
        ("plugin-manifest", PluginManifest.model_json_schema()),
    ):
        path = TARGET / f"{name}.schema.json"
        path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
