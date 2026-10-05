from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from qtpy import QtWidgets

from redsun import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    """Return settings stored in a file under the test's temporary directory."""
    return Settings(tmp_path / "session.json")


@pytest.fixture
def parent(qapp: QtWidgets.QApplication) -> Generator[QtWidgets.QWidget, None, None]:
    """Yield an empty widget to parent a view, and delete it after the test."""
    widget = QtWidgets.QWidget()
    yield widget
    widget.close()
    widget.deleteLater()
