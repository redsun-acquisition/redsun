from __future__ import annotations

import importlib
from importlib.util import find_spec
from typing import TYPE_CHECKING

import numpy as np
import pytest

from docs.examples.background_processing import MedianPresenter

if TYPE_CHECKING:
    from pathlib import Path

    from numpy.typing import NDArray
    from qtpy.QtWidgets import QApplication

    from redsun.compute import ThreadExecutor

BOX_EXAMPLES = ["box_detector"] if find_spec("sharedbox") else []

EXAMPLES = [
    "acquisition",
    "acquisition_files",
    "background_processing",
    "connect_on_demand",
    "console_frontend",
    "continuous_areadetector",
    "continuous_camera",
    "continuous_plan",
    "lights",
    "log_view",
    "napari_style",
    "positioner",
    "positioner_custom",
    *BOX_EXAMPLES,
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


# --8<-- [start:test]
def test_the_median_follows_the_run(inline_threads: ThreadExecutor) -> None:
    """Publish the median of a run's frames when the run stops."""
    presenter = MedianPresenter("median", inline_threads, source="camera")
    published: list[NDArray[np.float64]] = []
    presenter.sig_median.connect(published.append)

    presenter("start", {"uid": "run", "time": 0.0})
    for value in (1, 2, 9):
        presenter("event", {"data": {"camera": np.full((4, 4), value)}})
    presenter("stop", {"run_start": "run", "time": 1.0})

    assert np.array_equal(published[-1], np.full((4, 4), 2))


# --8<-- [end:test]
