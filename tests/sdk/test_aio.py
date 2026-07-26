"""Tests for the shared event loop and the culsans-backed psygnal backend."""

from __future__ import annotations

import asyncio
import gc
import logging
import threading
import time
import warnings
from typing import TYPE_CHECKING, Any

import psygnal._async
import pytest
from bluesky.run_engine import _ensure_event_loop_running
from culsans import QueueShutDown
from psygnal import Signal, get_async_backend
from psygnal._async import AsyncioBackend, _AsyncBackend, clear_async_backend
from psygnal._weak_callback import StrongCoroutineFunction, WeakCoroutineMethod

from redsun import aio
from redsun.aio import (
    AwaitableEvent,
    CulsansAsyncioBackend,
    _loop_factory,
    get_shared_loop,
    run_coro,
    set_async_backend,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from psygnal._async import QueueItem, SupportedBackend

TIMEOUT = 5.0


def wait_until(predicate: Callable[[], bool], timeout: float = TIMEOUT) -> bool:
    """Poll ``predicate`` from the calling thread until it holds or time runs out."""
    deadline = time.perf_counter() + timeout
    while time.perf_counter() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


class Emitter:
    sig_motor_move = Signal(str, str, float)


class ForeignBackend(_AsyncBackend):
    """Stand-in for a backend redsun did not install."""

    def __init__(self) -> None:
        super().__init__("trio")
        self._running = AwaitableEvent()

    @property
    def running(self) -> AwaitableEvent:
        return self._running

    def put(self, item: QueueItem) -> None: ...

    async def run(self) -> None: ...


@pytest.fixture(autouse=True)
def clean_backend() -> Iterator[None]:
    """Start and end every test with no async backend installed."""
    clear_async_backend()
    try:
        yield
    finally:
        clear_async_backend()


@pytest.fixture
def backend() -> CulsansAsyncioBackend:
    return set_async_backend()


def test_set_async_backend_installs_into_psygnal(
    backend: CulsansAsyncioBackend,
) -> None:
    assert get_async_backend() is backend
    assert backend._backend == "culsans"
    assert backend.name == "psygnal-culsans"


def test_set_async_backend_returns_a_running_backend() -> None:
    """The drain starts on another thread, so this must not be observably async."""
    for _ in range(50):
        installed = set_async_backend()
        assert installed.running.is_set()
        clear_async_backend()


def test_set_async_backend_is_idempotent(backend: CulsansAsyncioBackend) -> None:
    assert set_async_backend() is backend


def test_set_async_backend_refuses_a_foreign_backend() -> None:
    psygnal._async._ASYNC_BACKEND = ForeignBackend()
    with pytest.raises(RuntimeError, match="already set to: trio"):
        set_async_backend()


@pytest.mark.parametrize("name", ["asyncio", "anyio", "trio"])
def test_psygnal_cannot_replace_our_backend(
    backend: CulsansAsyncioBackend, name: SupportedBackend
) -> None:
    with pytest.raises(RuntimeError, match="already set to: culsans"):
        psygnal._async.set_async_backend(name)


def test_backend_is_subclass_and_virtual_subclass(
    backend: CulsansAsyncioBackend,
) -> None:
    # real inheritance keeps the ABC contract and mypy happy...
    assert issubclass(CulsansAsyncioBackend, _AsyncBackend)
    # ...while the virtual registration is what psygnal's teardown dispatches on
    assert issubclass(CulsansAsyncioBackend, AsyncioBackend)
    assert isinstance(get_async_backend(), AsyncioBackend)


def test_clear_async_backend_closes_the_queue(
    backend: CulsansAsyncioBackend,
) -> None:
    clear_async_backend()

    assert get_async_backend() is None
    assert wait_until(lambda: not backend.running.is_set())
    with pytest.raises(QueueShutDown):
        backend.put((None, ()))  # type: ignore[arg-type]


def test_connecting_a_coroutine_without_a_backend_raises() -> None:
    async def on_move(motor: str, axis: str, position: float) -> None: ...

    with pytest.raises(RuntimeError, match="No async backend set"):
        Emitter().sig_motor_move.connect(on_move)


def test_connect_coroutine_method_does_not_warn(
    backend: CulsansAsyncioBackend,
) -> None:
    class Presenter:
        async def move(self, motor: str, axis: str, position: float) -> None: ...

    emitter, presenter = Emitter(), Presenter()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        emitter.sig_motor_move.connect(presenter.move)

    assert [w for w in caught if issubclass(w.category, RuntimeWarning)] == []
    assert isinstance(emitter.sig_motor_move._slots[-1], WeakCoroutineMethod)


def test_connect_coroutine_function(backend: CulsansAsyncioBackend) -> None:
    async def on_move(motor: str, axis: str, position: float) -> None: ...

    emitter = Emitter()
    emitter.sig_motor_move.connect(on_move)
    assert isinstance(emitter.sig_motor_move._slots[-1], StrongCoroutineFunction)


def test_emit_from_foreign_thread_reaches_an_idle_loop(
    backend: CulsansAsyncioBackend,
) -> None:
    delivered = threading.Event()
    seen: list[tuple[Any, ...]] = []

    async def on_move(motor: str, axis: str, position: float) -> None:
        seen.append((motor, axis, position, asyncio.get_running_loop()))
        delivered.set()

    emitter = Emitter()
    emitter.sig_motor_move.connect(on_move)

    # the loop has nothing else to do — this is the case a non-threadsafe
    # ``put_nowait`` never wakes up
    emitter.sig_motor_move.emit("stage", "x", 10.0)

    assert delivered.wait(TIMEOUT)
    motor, axis, position, loop = seen[0]
    assert (motor, axis, position) == ("stage", "x", 10.0)
    assert loop is get_shared_loop()


def test_slots_run_concurrently_not_serialized(
    backend: CulsansAsyncioBackend,
) -> None:
    done = threading.Event()
    order: list[str] = []

    async def on_move(motor: str, axis: str, position: float) -> None:
        if axis == "slow":
            await asyncio.sleep(0.3)
        order.append(axis)
        if axis == "slow":
            done.set()

    emitter = Emitter()
    emitter.sig_motor_move.connect(on_move)

    start = time.perf_counter()
    emitter.sig_motor_move.emit("stage", "slow", 1.0)
    emitter.sig_motor_move.emit("stage", "y", 2.0)
    emitter.sig_motor_move.emit("stage", "z", 3.0)

    assert done.wait(TIMEOUT)
    elapsed = time.perf_counter() - start

    assert order == ["y", "z", "slow"]
    assert elapsed < 0.9, "slow slot serialized the fast ones"


def test_raising_slot_is_logged_and_dispatch_survives(
    backend: CulsansAsyncioBackend, caplog: pytest.LogCaptureFixture
) -> None:
    delivered = threading.Event()
    seen: list[float] = []

    async def on_move(motor: str, axis: str, position: float) -> None:
        if position < 0:
            raise ValueError("out of range")
        seen.append(position)
        delivered.set()

    emitter = Emitter()
    emitter.sig_motor_move.connect(on_move)

    with caplog.at_level(logging.ERROR, logger="redsun"):
        emitter.sig_motor_move.emit("stage", "x", -1.0)
        assert wait_until(lambda: "Exception in async slot" in caplog.text)

        emitter.sig_motor_move.emit("stage", "x", 42.0)
        assert delivered.wait(TIMEOUT)

    record = next(r for r in caplog.records if "async slot" in r.message)
    assert record.exc_info is not None
    assert "out of range" in caplog.text
    assert seen == [42.0]
    assert backend.running.is_set()


def test_cancelled_slot_is_not_logged(
    backend: CulsansAsyncioBackend, caplog: pytest.LogCaptureFixture
) -> None:
    started, cancelled = threading.Event(), threading.Event()

    async def on_move(motor: str, axis: str, position: float) -> None:
        started.set()
        try:
            await asyncio.sleep(TIMEOUT)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    emitter = Emitter()
    emitter.sig_motor_move.connect(on_move)

    with caplog.at_level(logging.ERROR, logger="redsun"):
        emitter.sig_motor_move.emit("stage", "x", 1.0)
        assert started.wait(TIMEOUT)
        # close() cancels the in-flight slot through the drain's exit path
        backend.close()
        assert cancelled.wait(TIMEOUT)
        assert wait_until(lambda: not backend.running.is_set())

    assert caplog.records == []


def test_queue_shutdown_is_not_an_error(
    backend: CulsansAsyncioBackend, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG, logger="redsun"):
        backend.close()
        assert wait_until(lambda: "queue shut down" in caplog.text)

    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []


def test_drain_cancellation_is_not_an_error(
    backend: CulsansAsyncioBackend, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG, logger="redsun"):
        assert backend._run_task.cancel()
        assert wait_until(lambda: "Dispatch cancelled" in caplog.text)

    assert [r for r in caplog.records if r.levelno >= logging.ERROR] == []


def test_unexpected_drain_failure_is_logged(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    calls: list[int] = []
    real_get_shared_loop = aio.get_shared_loop

    def flaky() -> asyncio.AbstractEventLoop:
        calls.append(1)
        # the first call comes from __init__, the second from run()
        if len(calls) > 1:
            raise RuntimeError("loop gone")
        return real_get_shared_loop()

    monkeypatch.setattr(aio, "get_shared_loop", flaky)

    with caplog.at_level(logging.ERROR, logger="redsun"):
        failing = set_async_backend()
        assert wait_until(lambda: "Dispatch stopped: loop gone" in caplog.text)

    record = next(r for r in caplog.records if "Dispatch stopped" in r.message)
    assert record.exc_info is not None
    assert not failing.running.is_set()


def test_dead_weak_callback_is_skipped(backend: CulsansAsyncioBackend) -> None:
    delivered = threading.Event()

    class Presenter:
        async def move(self, motor: str, axis: str, position: float) -> None:
            delivered.set()

    emitter, presenter = Emitter(), Presenter()
    emitter.sig_motor_move.connect(presenter.move)
    del presenter
    gc.collect()

    emitter.sig_motor_move.emit("stage", "x", 1.0)
    assert not delivered.wait(0.3)

    # the drain is still consuming after dereference() returned None
    alive = threading.Event()

    async def on_move(motor: str, axis: str, position: float) -> None:
        alive.set()

    emitter.sig_motor_move.connect(on_move)
    emitter.sig_motor_move.emit("stage", "x", 2.0)
    assert alive.wait(TIMEOUT)


@pytest.mark.parametrize("run", [1, 2])
async def test_delivery_survives_per_test_event_loops(
    backend: CulsansAsyncioBackend, run: int
) -> None:
    """An ``asyncio.Queue`` would bind to the first loop and fail the second."""
    delivered = threading.Event()

    async def on_move(motor: str, axis: str, position: float) -> None:
        delivered.set()

    emitter = Emitter()
    emitter.sig_motor_move.connect(on_move)
    emitter.sig_motor_move.emit("stage", "x", float(run))

    assert await asyncio.get_running_loop().run_in_executor(
        None, delivered.wait, TIMEOUT
    )
    assert asyncio.get_running_loop() is not get_shared_loop()


def test_run_does_not_start_a_second_drain(backend: CulsansAsyncioBackend) -> None:
    """A second ``run()`` must return, not park on the queue alongside the first."""
    run_coro(asyncio.wait_for(backend.run(), TIMEOUT))
    assert backend.running.is_set()


def test_close_stops_the_drain(backend: CulsansAsyncioBackend) -> None:
    backend.close()

    assert wait_until(lambda: not backend.running.is_set())
    with pytest.raises(QueueShutDown):
        backend.put((None, ()))  # type: ignore[arg-type]


def test_close_is_idempotent(backend: CulsansAsyncioBackend) -> None:
    backend.close()
    backend.close()
    assert wait_until(lambda: not backend.running.is_set())


def test_backend_buffers_items_put_before_the_drain_runs() -> None:
    delivered = threading.Event()

    async def on_move(motor: str, axis: str, position: float) -> None:
        delivered.set()

    set_async_backend()
    emitter = Emitter()
    emitter.sig_motor_move.connect(on_move)

    # no wait on `running` — the queue must hold the item until the drain
    # is scheduled on the shared loop
    emitter.sig_motor_move.emit("stage", "x", 1.0)
    assert delivered.wait(TIMEOUT)


def test_awaitable_event_set_and_clear() -> None:
    event = AwaitableEvent()
    assert not event.is_set()
    event.set()
    assert event.is_set()
    event.clear()
    assert not event.is_set()


async def test_awaitable_event_wait_returns_when_already_set() -> None:
    event = AwaitableEvent()
    event.set()
    await asyncio.wait_for(event.wait(), TIMEOUT)


async def test_awaitable_event_wait_wakes_on_a_cross_thread_set() -> None:
    event = AwaitableEvent()
    threading.Timer(0.05, event.set).start()
    await asyncio.wait_for(event.wait(), TIMEOUT)
    assert event.is_set()


def test_shared_loop_is_a_running_singleton() -> None:
    loop = get_shared_loop()
    assert get_shared_loop() is loop
    assert _loop_factory.loop is loop
    assert loop.is_running()
    assert _loop_factory._thread is not threading.current_thread()


def test_shared_loop_is_known_to_the_bluesky_loop_cache() -> None:
    loop = get_shared_loop()
    assert _ensure_event_loop_running.loop_to_thread[loop] is _loop_factory._thread  # type: ignore[attr-defined]


def test_run_coro_returns_the_result() -> None:
    async def answer() -> int:
        await asyncio.sleep(0)
        return 42

    assert run_coro(answer()) == 42


def test_run_coro_runs_on_the_shared_loop() -> None:
    async def which_loop() -> asyncio.AbstractEventLoop:
        return asyncio.get_running_loop()

    assert run_coro(which_loop()) is get_shared_loop()


def test_run_coro_returns_a_future() -> None:
    async def answer() -> int:
        return 42

    future = run_coro(answer(), return_future=True)
    assert future.result(TIMEOUT) == 42


def test_run_coro_propagates_exceptions() -> None:
    async def boom() -> None:
        raise ValueError("out of range")

    with pytest.raises(ValueError, match="out of range"):
        run_coro(boom())
