from pathlib import Path

import pytest

from redsun.aio import run_coro
from redsun.engine import RunEngine
from redsun.virtual import VirtualContainer

from .mocks import MockDetector


@pytest.fixture
def config_path() -> Path:
    return Path(__file__).parent / "data"


@pytest.fixture(scope="function")
def RE() -> RunEngine:
    return RunEngine()


@pytest.fixture(scope="function")
def detector() -> MockDetector:
    """Return a connected soft-signal detector, for plans the ``RE`` fixture runs.

    Connected on the shared loop, which is the one the engine runs its plans
    on: a device connected anywhere else is bound to a loop the engine never
    touches.
    """
    device = MockDetector("det1")
    run_coro(device.connect())
    return device


@pytest.fixture(scope="function")
def bus() -> VirtualContainer:
    # containers are fully instance-scoped; no shared state to reset
    return VirtualContainer()
