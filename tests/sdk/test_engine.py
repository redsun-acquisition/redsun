from __future__ import annotations

import asyncio
import subprocess
import sys
import threading
from concurrent.futures import wait
from typing import TYPE_CHECKING, Any

import bluesky.plan_stubs as bps
import pytest
from bluesky.plans import count
from bluesky.utils import RunEngineInterrupted

from redsun.aio import get_shared_loop, run_coro
from redsun.engine import RunEngine, RunEngineResult
from tests.sdk.mocks import MockDetector

if TYPE_CHECKING:
    from collections.abc import Callable

    from bluesky.utils import MsgGenerator


def _engine_threads() -> set[threading.Thread]:
    return {t for t in threading.enumerate() if t.name == "RunEngine"}


def _running(engine: RunEngine) -> threading.Event:
    """Return an event set the moment the engine reports itself running."""
    running = threading.Event()

    def on_state(new: str, old: str) -> None:
        if new == "running":
            running.set()

    engine.sig_state_changed.connect(on_state)
    return running


async def _current_thread() -> threading.Thread:
    return threading.current_thread()


def _recorder(
    seen: list[tuple[str, str, threading.Thread]], subscription: str
) -> Callable[[str, dict[str, Any]], None]:
    """Return a document callback appending what it receives to *seen*."""

    def callback(name: str, doc: dict[str, Any]) -> None:
        seen.append((subscription, name, threading.current_thread()))

    return callback


def test_each_plan_runs_on_a_thread_that_ends_with_it(
    RE: RunEngine, detector: MockDetector
) -> None:
    """Run each plan on its own thread that ends when the plan does."""
    before = _engine_threads()
    during: list[threading.Thread] = []

    def plan() -> MsgGenerator[Any]:
        # looked for while the plan runs: a short plan can end, and its thread
        # with it, before the caller gets to look
        during.extend(_engine_threads() - before)
        return (yield from count([detector], num=1))

    wait([RE(plan())])
    (worker,) = during
    worker.join(timeout=5)

    assert not worker.is_alive()


def test_abort_ends_the_running_plan_and_its_thread(RE: RunEngine) -> None:
    """End the running plan and its thread on abort."""
    before = _engine_threads()
    running = _running(RE)
    fut = RE(bps.sleep(10.0))
    (worker,) = _engine_threads() - before
    assert running.wait(5)

    RE.abort()
    worker.join(timeout=5)

    with pytest.raises(RunEngineInterrupted):
        fut.result(timeout=5)
    assert not worker.is_alive()


def test_an_engine_runs_on_the_shared_loop_by_default(RE: RunEngine) -> None:
    """Use the shared loop when no loop is given."""
    assert RE.loop is get_shared_loop()


def test_importing_the_engine_starts_no_thread() -> None:
    """Start no thread when the engine module is imported."""
    probe = (
        "import threading, redsun.engine; "
        "print(sorted(t.name for t in threading.enumerate()))"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    )

    assert result.stdout.strip() == "['MainThread']"


def test_subscribed_callbacks_receive_their_documents_on_the_loop_thread(
    RE: RunEngine, detector: MockDetector
) -> None:
    """Send each subscriber its documents, on the shared loop's thread."""
    seen: list[tuple[str, str, threading.Thread]] = []
    RE.subscribe(_recorder(seen, "all"))
    for name in ("start", "descriptor", "event", "stop"):
        RE.subscribe(_recorder(seen, name), name)

    result = RE(count([detector], num=2)).result(timeout=10)
    assert isinstance(result, RunEngineResult)
    assert result.exit_status == "success"

    by_subscription = {
        subscription: [name for key, name, _ in seen if key == subscription]
        for subscription in ("all", "start", "descriptor", "event", "stop")
    }
    assert by_subscription == {
        "all": ["start", "descriptor", "event", "event", "stop"],
        "start": ["start"],
        "descriptor": ["descriptor"],
        "event": ["event", "event"],
        "stop": ["stop"],
    }
    assert {thread for _, _, thread in seen} == {run_coro(_current_thread())}


def test_pausable_engine(
    RE: RunEngine, detector: MockDetector, wait_until: Callable[..., bool]
) -> None:
    """Interrupt a plan at a checkpoint with no message, resume it, then stop it."""

    def pausable_plan() -> Any:
        yield from bps.checkpoint()

        yield from count([detector], num=None)

    running = _running(RE)
    fut = RE(pausable_plan())
    assert running.wait(5)

    RE.request_pause(defer=True)
    with pytest.raises(RunEngineInterrupted) as interrupted:
        fut.result(timeout=5)
    assert str(interrupted.value) == ""
    assert RE.state == "paused"

    resumed = RE.resume()
    assert wait_until(lambda: RE.state == "running", timeout=5)
    stopped = RE.stop().result(timeout=5)

    with pytest.raises(RunEngineInterrupted):
        resumed.result(timeout=5)
    assert isinstance(stopped, RunEngineResult)
    assert stopped.exit_status == "success"


def test_the_engine_announces_each_state_change(RE: RunEngine) -> None:
    """Emit each state change as a (new, old) pair through pause, resume and end."""
    seen: list[tuple[str, str]] = []
    RE.sig_state_changed.connect(lambda new, old: seen.append((new, old)))

    def plan() -> Any:
        yield from bps.checkpoint()
        yield from bps.pause()
        yield from bps.null()

    with pytest.raises(RunEngineInterrupted):
        RE(plan()).result(timeout=5)
    RE.resume().result(timeout=5)

    assert seen == [
        ("running", "idle"),
        ("pausing", "running"),
        ("paused", "pausing"),
        ("running", "paused"),
        ("idle", "running"),
    ]


def test_stopping_a_paused_plan_runs_its_cleanup_off_the_caller_thread(
    RE: RunEngine,
) -> None:
    """Return from `stop` while a paused plan's cleanup is still running."""
    returned = asyncio.Event()
    waited: list[bool] = []

    async def wait_for_the_caller() -> None:
        try:
            await asyncio.wait_for(returned.wait(), timeout=5)
        except TimeoutError:
            waited.append(False)
        else:
            waited.append(True)

    def plan() -> Any:
        try:
            yield from bps.checkpoint()
            yield from bps.pause()
        finally:
            yield from bps.wait_for([wait_for_the_caller])

    with pytest.raises(RunEngineInterrupted):
        RE(plan()).result(timeout=5)

    stopping = RE.stop()
    RE.loop.call_soon_threadsafe(returned.set)
    stopping.result(timeout=10)

    assert waited == [True]
    assert RE.state == "idle"
