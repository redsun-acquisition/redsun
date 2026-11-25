"""Tests for the script writing the example's OpenAPI document."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from scripts.export_openapi import main

if TYPE_CHECKING:
    from pathlib import Path


def test_the_script_writes_the_served_paths(tmp_path: Path) -> None:
    """Write the paths of the served presenters and the arguments of their signals."""
    target = tmp_path / "openapi.json"

    main([str(target)])

    document = json.loads(target.read_text(encoding="utf-8"))
    assert {"/api/positioner/move", "/api/lights/lights"} <= set(document["paths"])
    assert set(document["x-redsun-signals"]) == {"positioner", "lights"}
