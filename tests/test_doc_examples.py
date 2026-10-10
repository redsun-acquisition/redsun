from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

    from qtpy.QtWidgets import QApplication

EXAMPLES = [
    "acquisition",
    "acquisition_files",
    "connect_on_demand",
    "console_frontend",
    "continuous_plan",
    "lights",
    "log_view",
    "napari_style",
    "positioner",
    "positioner_custom",
]


@pytest.mark.qt
@pytest.mark.parametrize("example", EXAMPLES)
def test_the_session_of_a_guide_builds_every_component(
    example: str, qapp: QApplication, tmp_path: Path, unstyled: None
) -> None:
    """Build every component of the example session of each guide."""
    app = importlib.import_module(f"docs.examples.{example}").MyApp
    session = app(
        {"mock": True, "strict": True, "storage": {"base_dir": str(tmp_path)}}
    ).build()
    session.shutdown()
