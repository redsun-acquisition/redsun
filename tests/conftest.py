import pytest
import sys
from pathlib import Path

@pytest.fixture
def config_path() -> Path:
    return Path(__file__).parent / "configs"

@pytest.fixture
def importlib_str() -> str:
    if sys.version_info < (3, 10):
        return "importlib_metadata"
    else:
        return "importlib.metadata"
