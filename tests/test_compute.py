"""A session hands its components executors and starts the pools behind them."""

from __future__ import annotations

import logging
import sys
import threading
from typing import TYPE_CHECKING

import pytest
from threadpoolctl import threadpool_info

from redsun import AsPresenter, RegistrationError, Session, provides
from redsun.compute import Future, ThreadExecutor, ThreadPool, ThreadPoolSettings

if TYPE_CHECKING:
    from redsun.testing import BuildSession

PRE_START = "the pool starts after every setup; use .then(...)"


class Median:
    """Presenter taking an executor in its constructor."""

    def __init__(self, name: str, executor: ThreadExecutor) -> None:
        self.name = name
        self.executor = executor


class SetupAsker:
    """Presenter asking for its executor in both its constructor and `setup`."""

    def __init__(self, name: str, executor: ThreadExecutor) -> None:
        self.name = name
        self.executor = executor
        self.from_setup: ThreadExecutor | None = None

    def setup(self, executor: ThreadExecutor) -> None:
        self.from_setup = executor


class Warmer:
    """Presenter submitting a call from `setup`."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.warmed = threading.Event()

    def setup(self, executor: ThreadExecutor) -> None:
        executor.submit(self.warmed.set)


class Waiter:
    """Presenter waiting for a result in `setup`, before the pool starts."""

    def __init__(self, name: str) -> None:
        self.name = name

    def setup(self, executor: ThreadExecutor) -> None:
        executor.submit(pow, 2, 3).result()


class Failing:
    """Presenter failing to build after asking for an executor."""

    def __init__(self, name: str, executor: ThreadExecutor) -> None:
        raise RuntimeError("no median today")


class Plain:
    """Presenter asking for nothing."""

    def __init__(self, name: str) -> None:
        self.name = name


class PoolAsker:
    """Presenter asking for a pool directly."""

    def __init__(self, name: str, pool: ThreadPool) -> None:
        self.name = name


class ExecutorSharer:
    """Presenter sharing an executor of its own."""

    def __init__(self, name: str) -> None:
        self.name = name

    @provides
    def executor(self) -> ThreadExecutor:
        raise AssertionError("never read")


class SlowCaller:
    """Presenter whose call finishes once its gate opens."""

    def __init__(self, name: str, executor: ThreadExecutor) -> None:
        self.name = name
        self.executor = executor
        self.gate = threading.Event()
        self.received: list[object] = []

    def start_slow(self) -> Future[bool]:
        future = self.executor.submit(self.gate.wait, 5)
        future.then(self.received.append)
        return future


class ShutdownLogger:
    """Presenter logging its own shutdown."""

    def __init__(self, name: str, executor: ThreadExecutor) -> None:
        self.name = name

    def shutdown(self) -> None:
        logging.getLogger("redsun.tests").info("logs shut down")


def watchdog_threads() -> list[threading.Thread]:
    """Return the watchdog threads alive."""
    return [t for t in threading.enumerate() if t.name == "redsun-watchdog"]


class OneMedian(Session):
    median: AsPresenter[Median]


class SetupAsks(Session):
    asks: AsPresenter[SetupAsker]


class Warms(Session):
    warms: AsPresenter[Warmer]


class WaitsInSetup(Session):
    waits: AsPresenter[Waiter]


class FailsAfterAsking(Session):
    fails: AsPresenter[Failing]
    plain: AsPresenter[Plain]


class NoCompute(Session):
    plain: AsPresenter[Plain]


class AsksForPool(Session):
    pool: AsPresenter[PoolAsker]


class ProvidesExecutor(Session):
    sharer: AsPresenter[ExecutorSharer]


class Slow(Session):
    slow: AsPresenter[SlowCaller]


class LogsShutdown(Session):
    logs: AsPresenter[ShutdownLogger]


def test_a_component_gets_an_executor_and_its_result(build: BuildSession) -> None:
    """Hand a presenter a ThreadExecutor whose call runs once the session has started its pool."""
    session = build(OneMedian)
    future = session.median.executor.submit(pow, 2, 3)
    assert future.result(timeout=5) == 8
    assert session.median.executor.pool_type is ThreadPool


def test_constructor_and_setup_share_one_executor(build: BuildSession) -> None:
    """Give a component one executor per kind, in its constructor and its setup alike."""
    session = build(SetupAsks)
    assert session.asks.from_setup is session.asks.executor


def test_setup_calls_wait_for_start(build: BuildSession) -> None:
    """Run a call submitted from setup once the pool starts."""
    session = build(Warms)
    assert session.warms.warmed.wait(timeout=5)


def test_setup_result_raises_and_component_stays_in_place(
    caplog: pytest.LogCaptureFixture, build: BuildSession
) -> None:
    """Refuse result() in setup with the pre-start message and keep the component, not set up."""
    with caplog.at_level(logging.WARNING, logger="redsun"):
        session = build(WaitsInSetup)
    assert "waits" in session.presenters
    assert f"Failed to set up presenter 'waits': {PRE_START}" in caplog.text


def test_pool_of_failed_component_never_starts(build: BuildSession) -> None:
    """Make but never start a pool whose only holder failed to build, and change no limit."""
    interval = sys.getswitchinterval()
    session = build(FailsAfterAsking, {"compute": {"switch_interval_ms": 1}})
    assert "fails" not in session.presenters
    assert sys.getswitchinterval() == interval


def test_session_without_executors_changes_nothing(
    build: BuildSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Make no pool, read no cores, and leave native limits and the switch interval as found."""

    def unread() -> int:
        raise AssertionError("the physical cores were read")

    monkeypatch.setattr("redsun.session._compute.physical_cores", unread)
    found = threadpool_info()
    interval = sys.getswitchinterval()
    session = build(NoCompute, {"compute": {"switch_interval_ms": 1}})
    assert session.pool_settings == {}
    assert threadpool_info() == found and sys.getswitchinterval() == interval


def test_limits_are_restored_at_shutdown(build: BuildSession) -> None:
    """Restore the switch interval once the session shuts down."""
    interval = sys.getswitchinterval()
    session = build(OneMedian, {"compute": {"switch_interval_ms": 1}})
    assert sys.getswitchinterval() == 0.001
    session.shutdown()
    assert sys.getswitchinterval() == interval


def test_the_file_lays_over_the_class(
    build: BuildSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Size the shared pool from the class's preset and the file's cores."""

    class Latency(OneMedian):
        compute = "latency"

    monkeypatch.setattr("redsun.session._compute.physical_cores", lambda: 8)
    session = build(Latency, {"compute": {"cores": 3}})
    assert session.pool_settings == {(ThreadPool, None): ThreadPoolSettings(1, 3)}


def test_asking_for_a_pool_names_the_executor(
    caplog: pytest.LogCaptureFixture, build: BuildSession
) -> None:
    """Skip a component asking for a pool, naming the executor to ask for instead."""
    with caplog.at_level(logging.WARNING, logger="redsun"):
        session = build(AsksForPool)
    assert "pool" not in session.presenters
    assert "ask for ThreadExecutor instead" in caplog.text


def test_providing_an_executor_is_refused(build: BuildSession) -> None:
    """Refuse a provider whose provided type is an executor."""
    with pytest.raises(
        RegistrationError, match="the session makes pools and executors"
    ):
        build(ProvidesExecutor)


def test_a_late_result_skips_a_released_component(build: BuildSession) -> None:
    """Drop the callback of a call that finishes after its owner shut down."""
    session = build(Slow)
    presenter = session.slow
    future = presenter.start_slow()
    done = threading.Event()
    future.add_done_callback(lambda _: done.set())
    session.shutdown()
    presenter.gate.set()
    assert done.wait(5)
    assert presenter.received == []


def test_the_pool_stops_after_its_components(
    build: BuildSession, caplog: pytest.LogCaptureFixture
) -> None:
    """Shut a component down before its pool's teardown logs the pool's summary."""
    caplog.set_level(logging.INFO, logger="redsun")
    session = build(LogsShutdown)
    session.shutdown()
    messages = [r.getMessage() for r in caplog.records]
    component = messages.index("logs shut down")
    pool = next(i for i, m in enumerate(messages) if m.startswith("thread pool:"))
    assert component < pool


def test_the_watchdog_runs_with_the_pools_and_stops_at_shutdown(
    build: BuildSession,
) -> None:
    """Run one watchdog thread while a pool runs, and none after shutdown."""
    session = build(OneMedian)
    assert len(watchdog_threads()) == 1
    session.shutdown()
    assert watchdog_threads() == []


def test_a_session_without_executors_starts_no_watchdog(build: BuildSession) -> None:
    """Start no watchdog thread when no component asks for an executor."""
    build(NoCompute)
    assert watchdog_threads() == []
