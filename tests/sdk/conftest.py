from pathlib import Path
from typing import Generator

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
def bus() -> Generator[VirtualContainer, None, None]:
    container = VirtualContainer()
    yield container
    container._config.reset()
