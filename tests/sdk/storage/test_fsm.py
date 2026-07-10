from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime

import pytest

from redsun.storage._fsm import InvalidStoreState, StorageState, StorageStateMachine


@dataclass
class PathData:
    plan: str
    session: str
    date: str


@pytest.fixture(scope="module")
def path_data() -> PathData:
    return PathData(
        plan="unknown", session="test_session", date=datetime.now().strftime("%Y-%m-%d")
    )


async def test_fsm_cycle() -> None:
    fsm = StorageStateMachine()
    assert fsm.state == StorageState.UNSEALED

    assert fsm.try_seal() is True
    assert fsm.state == StorageState.SEALING  # type: ignore

    task = asyncio.create_task(fsm.await_open())  # type: ignore
    await asyncio.sleep(0.1)  # Allow the task to start and wait

    fsm.open_succeeded()

    await task
    assert fsm.state == StorageState.OPEN
    assert fsm._closed.is_set() is False
    assert fsm._opened.is_set() is True

    fsm.begin_close()
    assert fsm.state == StorageState.CLOSING
    fsm.close_finished()
    assert fsm.state == StorageState.UNSEALED


async def test_fsm_invalid_open() -> None:
    fsm = StorageStateMachine()
    assert fsm.state == StorageState.UNSEALED

    with pytest.raises(InvalidStoreState) as exc_info:
        fsm.open_succeeded()
        assert exc_info.value.state == StorageState.UNSEALED
        assert exc_info.value.verb == "confirm open"

    with pytest.raises(InvalidStoreState) as exc_info:
        fsm.open_failed(RuntimeError())
        assert exc_info.value.state == StorageState.UNSEALED
        assert exc_info.value.verb == "fail open"

    with pytest.raises(InvalidStoreState) as exc_info:
        fsm.begin_close()
        assert exc_info.value.state == StorageState.UNSEALED
        assert exc_info.value.verb == "close"


async def test_state_machine_open_failed() -> None:
    fsm = StorageStateMachine()
    assert fsm.state == StorageState.UNSEALED

    assert fsm.try_seal() is True
    assert fsm.state == StorageState.SEALING  # type: ignore

    exc = RuntimeError()  # type: ignore
    fsm.open_failed(exc)

    assert fsm.state == StorageState.UNSEALED
    assert fsm._open_exc is exc


async def test_fsm_await_open_with_exception() -> None:
    fsm = StorageStateMachine()
    assert fsm.state == StorageState.UNSEALED

    assert fsm.try_seal() is True
    assert fsm.state == StorageState.SEALING  # type: ignore

    exc = RuntimeError("Test exception")  # type: ignore
    fsm.open_failed(exc)

    with pytest.raises(RuntimeError) as exc_info:
        await fsm.await_open()
        assert str(exc_info.value) == "Test exception"


async def test_fsm_seal_after_closing() -> None:
    fsm = StorageStateMachine()
    assert fsm.state == StorageState.UNSEALED

    assert fsm.try_seal() is True
    assert fsm.state == StorageState.SEALING  # type: ignore

    fsm.open_succeeded()  # type: ignore
    assert fsm.state == StorageState.OPEN

    fsm.begin_close()
    assert fsm.state == StorageState.CLOSING

    with pytest.raises(InvalidStoreState) as exc_info:
        fsm.try_seal()
        assert exc_info.value.state == StorageState.CLOSING
        assert exc_info.value.verb == "seal"


async def test_fsm_open_after_open() -> None:
    fsm = StorageStateMachine()
    assert fsm.state == StorageState.UNSEALED

    assert fsm.try_seal() is True
    assert fsm.state == StorageState.SEALING  # type: ignore

    fsm.open_succeeded()  # type: ignore
    assert fsm.state == StorageState.OPEN

    with pytest.raises(InvalidStoreState) as exc_info:
        fsm.open_succeeded()
        assert exc_info.value.state == StorageState.OPEN
        assert exc_info.value.verb == "confirm open"

    with pytest.raises(InvalidStoreState) as exc_info:
        fsm.open_failed(RuntimeError())
        assert exc_info.value.state == StorageState.OPEN
        assert exc_info.value.verb == "fail open"


async def test_fsm_close_after_unsealed() -> None:
    fsm = StorageStateMachine()
    assert fsm.state == StorageState.UNSEALED

    with pytest.raises(InvalidStoreState) as exc_info:
        fsm.begin_close()
        assert exc_info.value.state == StorageState.UNSEALED
        assert exc_info.value.verb == "close"

    with pytest.raises(InvalidStoreState) as exc_info:
        fsm.close_finished()
        assert exc_info.value.state == StorageState.UNSEALED
        assert exc_info.value.verb == "close"
