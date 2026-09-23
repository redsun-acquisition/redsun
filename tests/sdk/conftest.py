from __future__ import annotations

from collections.abc import Iterator

import pytest

from redsun.aio import run_coro
from redsun.engine import RunEngine

from .mocks import MockDetector


@pytest.fixture
def RE() -> Iterator[RunEngine]:
    """Yield an engine, and abort whatever plan the test left running or paused."""
    engine = RunEngine()
    yield engine
    if engine.state != "idle":
        engine.abort()


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
