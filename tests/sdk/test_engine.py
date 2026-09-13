import subprocess
import sys
import threading
from concurrent.futures import Future, wait
from time import monotonic, sleep
from typing import Any

import bluesky.plan_stubs as bps
import pytest
from bluesky.plans import count
from bluesky.utils import RunEngineInterrupted

from redsun.aio import get_shared_loop
from redsun.engine import RunEngine, RunEngineResult

from .mocks import MockDetector


def test_engine_wrapper_construction(RE: RunEngine) -> None:
    assert RE.context_managers == []
    assert RE.pause_msg == ""


def _engine_threads() -> set[threading.Thread]:
    return {t for t in threading.enumerate() if t.name == "RunEngine"}


def _wait_until_running(engine: RunEngine) -> None:
    deadline = monotonic() + 5.0
    while engine.state != "running" and monotonic() < deadline:
        sleep(0.01)


def test_each_plan_runs_on_a_thread_that_ends_with_it(
    RE: RunEngine, detector: MockDetector
) -> None:
    before = _engine_threads()

    fut = RE(count([detector], num=1))
    (worker,) = _engine_threads() - before
    wait([fut])
    worker.join(timeout=5)

    assert not worker.is_alive()


def test_abort_ends_the_running_plan_and_its_thread(RE: RunEngine) -> None:
    """Bluesky's abort reaches a plan running on the engine's own thread."""
    before = _engine_threads()
    fut = RE(bps.sleep(10.0))
    (worker,) = _engine_threads() - before
    _wait_until_running(RE)

    RE.abort()
    worker.join(timeout=5)

    with pytest.raises(RunEngineInterrupted):
        fut.result(timeout=5)
    assert not worker.is_alive()


def test_an_engine_runs_on_the_shared_loop_by_default(RE: RunEngine) -> None:
    assert RE.loop is get_shared_loop()


def test_importing_the_engine_starts_no_thread() -> None:
    """The shared loop and its thread wait for the first engine that needs them."""
    probe = (
        "import threading, redsun.engine; "
        "print(sorted(t.name for t in threading.enumerate()))"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    )

    assert result.stdout.strip() == "['MainThread']"


def test_engine_wrapper_run(RE: RunEngine, detector: MockDetector) -> None:
    RE._call_returns_result = False
    fut = RE(count([detector], num=5))

    wait([fut])

    result = fut.result()

    assert type(result) is tuple
    assert len(result) == 1


def test_engine_wrapper_run_with_result(RE: RunEngine, detector: MockDetector) -> None:
    fut = RE(count([detector], num=5))

    wait([fut])

    result = fut.result()

    assert type(result) is RunEngineResult
    assert result.exit_status == "success"

    RE._call_returns_result = False


def test_engine_with_callback(RE: RunEngine, detector: MockDetector) -> None:
    def callback(future: Future[Any]) -> None:
        assert len(future.result()) == 1

    fut = RE(count([detector], num=5))
    fut.add_done_callback(callback)

    wait([fut])


def test_engine_callbacks(RE: RunEngine, detector: MockDetector) -> None:
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

    fut = RE(count([detector], num=5))
    wait([fut])

    counter = 0

    def callback(name: str, doc: dict[str, Any]) -> None:
        nonlocal counter
        counter += 1

    token = RE.subscribe(callback)
    RE.unsubscribe(token)

    fut = RE(count([detector], num=5))
    wait([fut])

    assert counter == 0


def test_pausable_engine(RE: RunEngine, detector: MockDetector) -> None:
    future_set = set()

    def pausable_plan() -> Any:
        yield from bps.checkpoint()

        yield from count([detector], num=None)

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
