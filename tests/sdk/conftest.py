from __future__ import annotations

import logging
from collections.abc import Iterator
from typing import TYPE_CHECKING

import pytest

from redsun.aio import run_coro
from redsun.engine import RunEngine
from tests.sdk.mocks import MockDetector

if TYPE_CHECKING:
    from bluesky.utils import Msg


@pytest.fixture
def RE() -> Iterator[RunEngine]:
    """Yield an engine, and abort whatever plan the test left running or paused."""
    engine = RunEngine()
    yield engine
    if engine.state != "idle":
        engine.abort().result(timeout=10)


@pytest.fixture(scope="function")
def detector() -> MockDetector:
    """Return a connected soft-signal detector, for plans the `RE` fixture runs.

    Connected on the shared loop, which is the one the engine runs its plans
    on: a device connected anywhere else is bound to a loop the engine never
    touches.
    """
    device = MockDetector("det1")
    run_coro(device.connect())
    return device


@pytest.fixture
def service_log(caplog: pytest.LogCaptureFixture) -> pytest.LogCaptureFixture:
    """Capture everything the `redsun` logger tree records, services included."""
    caplog.set_level(logging.DEBUG, logger="redsun")
    return caplog


@pytest.fixture
def polls(RE: RunEngine) -> list[Msg]:
    """Return a list gaining every poll for an action that `RE` runs.

    A second poll says the first found nothing asked for.
    """
    seen: list[Msg] = []

    def on_message(msg: Msg) -> None:
        if msg.command == "wait_for_actions":
            seen.append(msg)

    RE.msg_hook = on_message  # type: ignore[assignment]
    return seen
