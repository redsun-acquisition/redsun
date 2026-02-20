from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add the test directory to sys.path so mock_pkg is importable
_tests_dir = str(Path(__file__).parent)
if _tests_dir not in sys.path:
    sys.path.insert(0, _tests_dir)


@pytest.fixture
def config_path() -> Path:
    """Return the path to test configuration files."""
    return Path(__file__).parent / "configs"
