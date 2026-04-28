import threading
from concurrent.futures import Future, wait
from time import sleep
from typing import Any

import bluesky.plan_stubs as bps
from bluesky.plans import count
from ophyd.sim import det1

from redsun.engine import RunEngine, RunEngineResult


def test_engine_wrapper_construction(RE: RunEngine) -> None:
    assert RE.context_managers == []
    assert RE.pause_msg == ""


def test_engine_wrapper_run(RE: RunEngine) -> None:
    RE._call_returns_result = False
    fut = RE(count([det1], num=5))

    wait([fut])

    result = fut.result()

    assert type(result) is tuple
    assert len(result) == 1


def test_engine_wrapper_run_with_result(RE: RunEngine) -> None:
    fut = RE(count([det1], num=5))

    wait([fut])

    result = fut.result()

    assert type(result) is RunEngineResult
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
