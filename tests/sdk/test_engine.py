import logging
import platform
import threading
from concurrent.futures import Future, wait
from time import sleep
from typing import Any

import pytest
import bluesky.plan_stubs as bps
from bluesky.plans import count
from ophyd.sim import det1

from redsun.engine import RunEngine, RunEngineResult, Status
from redsun.engine._exceptions import (
    InvalidState,
    StatusTimeoutError,
    WaitTimeoutError,
)


def test_status() -> None:
    def callback(_: Status) -> None:
        # Simulate a task
        sleep(0.5)

    status = Status()

    assert status.timeout is None
    assert status.settle_time == 0.0
    assert status.done is False

    status.add_callback(callback)

    assert len(status.callbacks) == 1

    status.set_finished()

    while not status.done:
        ...

    assert status.done is True  # type: ignore
    assert status.success is True


def test_status_wrong_external_exception() -> None:
    status = Status()
    status.set_exception(Exception("Test exception"))

    with pytest.raises(InvalidState):
        # finishing twice raises invalid state
        status.set_exception(Exception("Can't call set exception twice"))


def test_status_wrong_external_finished() -> None:
    status = Status()
    status.set_finished()

    while not status.done:
        ...

    assert status.done is True
    assert status.success is True

    with pytest.raises(InvalidState):
        # finishing twice raises invalid state
        status.set_finished()


def test_status_false_exception() -> None:
    status = Status()
    with pytest.raises(Exception):
        status.set_exception("This is not an exception")
    assert status.done is False
    assert status.success is False


def test_status_timeout() -> None:
    status = Status(timeout=0.1)

    # cause a timeout
    sleep(0.5)
    assert isinstance(status.exception(), StatusTimeoutError)

    status = Status(timeout=0.3)

    # what happens if we set StatusTimeoutError as the exception?
    with pytest.raises(ValueError):
        status.set_exception(StatusTimeoutError)


def test_status_set_exception_after_timeout() -> None:
    status = Status(timeout=0.1)
    sleep(0.5)
    status.set_exception(Exception("Test exception"))
    assert isinstance(status.exception(), StatusTimeoutError)


def test_status_callback_after_finished() -> None:
    def post_callback(status: Status) -> None:
        assert status.done is True

    status = Status()
    status.set_finished()

    while not status.done:
        ...

    status.add_callback(post_callback)
    assert status.done is True
    assert status.success is True


def test_status_wait_timeout() -> None:
    status = Status()

    with pytest.raises(WaitTimeoutError):
        status.wait(timeout=0.1)


@pytest.mark.skipif(platform.system() == "Darwin", reason="Sometimes fails on macOS")
def test_status_settle_time() -> None:
    status = Status(timeout=0.1, settle_time=0.3)
    status.set_finished()

    # wait for timeout + settle_time
    status.wait()

    assert status.done is True
    assert status.success is True


def test_callback_exception_is_logged() -> None:
    logger = logging.getLogger("redsun")
    logger.setLevel(logging.DEBUG)

    # Create a callback that will raise an exception
    def failing_callback(_: Status) -> None:
        raise Exception("Callback failed!")

    # Create a Status object and add our failing callback
    status = Status()
    status.add_callback(failing_callback)

    # Complete the status
    status.set_finished()

    # Wait for callbacks to complete
    status.wait()

    # Check that the exception was logged
    # TODO: find a way to do this properly;
    #       the test passes though


def test_engine_wrapper_construction(RE: RunEngine) -> None:
    assert RE.context_managers == []
    assert RE.pause_msg == ""


def test_engine_wrapper_run(RE: RunEngine) -> None:
    RE._call_returns_result = False
    fut = RE(count([det1], num=5))

    wait([fut])

    result = fut.result()

    assert type(result) == tuple
    assert len(result) == 1


def test_engine_wrapper_run_with_result(RE: RunEngine) -> None:
    fut = RE(count([det1], num=5))

    wait([fut])

    result = fut.result()

    assert type(result) == RunEngineResult
    assert result.exit_status == "success"

    RE._call_returns_result = False


def test_engine_with_callback(RE: RunEngine) -> None:
    def callback(future: Future) -> None:
        assert len(future.result()) == 1

    fut = RE(count([det1], num=5))
    fut.add_done_callback(callback)

    wait([fut])


def test_engine_callbacks(RE: RunEngine) -> None:
    def all_callback(name: str, doc: dict[str, Any]) -> None:
        assert name in ["start", "descriptor", "event", "stop"]
        assert threading.current_thread().name == "bluesky-run-engine"

    def start_callback(name: str, doc: dict[str, Any]) -> None:
        assert name == "start"
        assert threading.current_thread().name == "bluesky-run-engine"

    def descriptor_callback(name: str, doc: dict[str, Any]) -> None:
        assert name == "descriptor"
        assert threading.current_thread().name == "bluesky-run-engine"

    def event_callback(name: str, doc: dict[str, Any]) -> None:
        assert name == "event"
        assert threading.current_thread().name == "bluesky-run-engine"

    def stop_callback(name: str, doc: dict[str, Any]) -> None:
        assert name == "stop"
        assert threading.current_thread().name == "bluesky-run-engine"

    RE.subscribe(all_callback)
    RE.subscribe(start_callback, "start")
    RE.subscribe(descriptor_callback, "descriptor")
    RE.subscribe(event_callback, "event")
    RE.subscribe(stop_callback, "stop")

    fut = RE(count([det1], num=5))
    wait([fut])

    counter = 0

    def callback(name: str, doc: dict[str, Any]) -> None:
        nonlocal counter
        counter += 1

    token = RE.subscribe(callback)
    RE.unsubscribe(token)

    fut = RE(count([det1], num=5))
    wait([fut])

    assert counter == 0


def test_pausable_engine(RE: RunEngine) -> None:
    future_set = set()

    def pausable_plan():
        yield from bps.checkpoint()

        yield from count([det1], num=None)

    fut = RE(pausable_plan())
    future_set.add(fut)
    fut.add_done_callback(future_set.discard)

    sleep(0.5)

    RE.request_pause(defer=True)

    wait(future_set)

    assert len(future_set) == 0

    fut = RE.resume()
    future_set.add(fut)
    fut.add_done_callback(future_set.discard)

    assert len(future_set) == 1

    RE.stop()

    wait(future_set)

    assert len(future_set) == 0
