from pathlib import Path

import pytest

from redsun.engine import RunEngine
from redsun.virtual import VirtualContainer


@pytest.fixture
def config_path() -> Path:
    return Path(__file__).parent / "data"


@pytest.fixture(scope="function")
def RE() -> RunEngine:
    return RunEngine()


@pytest.fixture(scope="function")
def bus() -> VirtualContainer:
    # containers are fully instance-scoped; no shared state to reset
    return VirtualContainer()
