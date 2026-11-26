"""Tests for the script writing the example's OpenAPI and AsyncAPI documents."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from scripts.export_openapi import main

if TYPE_CHECKING:
    from pathlib import Path


def test_the_script_writes_the_served_paths_and_signals(tmp_path: Path) -> None:
    """Write the paths of the served presenters and a message per signal they serve."""
    main([str(tmp_path)])

    openapi = json.loads((tmp_path / "openapi.json").read_text(encoding="utf-8"))
    asyncapi = json.loads((tmp_path / "asyncapi.json").read_text(encoding="utf-8"))
    assert {"/api/positioner/move", "/api/lights/lights"} <= set(openapi["paths"])
    readback = asyncapi["components"]["messages"]["positioner.sig_readback"]
    assert [a["type"] for a in readback["payload"]["properties"]["args"]["items"]] == [
        "string",
        "string",
        "number",
    ]
