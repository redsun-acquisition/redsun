"""Components get executors over one pool the session builds, sizes and stops."""

from __future__ import annotations

import logging
import sys
import threading
from typing import TYPE_CHECKING, Annotated, ClassVar

import pytest
from psygnal import emit_queued
from threadpoolctl import threadpool_info

from redsun import AsPresenter, Declare, Session
from redsun.compute import ThreadExecutor, deliver
from redsun.qt import QtSession

if TYPE_CHECKING:
    from collections.abc import Callable

    from qtpy.QtWidgets import QApplication

    from redsun.testing import BuildSession


class Summing:
    """Presenter taking an executor in its constructor."""

    def __init__(self, name: str, pool: ThreadExecutor) -> None:
        self.name, self.pool = name, pool


class SetupAsks:
    """Presenter asking for an executor in `setup`."""

    def __init__(self, name: str) -> None:
        self.name = name

    def setup(self, pool: ThreadExecutor) -> None:
        self.pool = pool


class ProviderAsks:
    """Provider asking for an executor in its constructor."""

    def __init__(self, pool: ThreadExecutor) -> None:
        self.pool = pool


class SummingApp(Session):
    summing: Annotated[AsPresenter[Summing], Declare()]


class TwoSummingApp(Session):
    first: Annotated[AsPresenter[Summing], Declare()]
    second: Annotated[AsPresenter[Summing], Declare()]


class LatencyAppWithSumming(Session):
    compute: ClassVar[dict[str, object]] = {
        "preset": "latency",
        "switch_interval_ms": 1.0,
    }

    summing: Annotated[AsPresenter[Summing], Declare()]


class LatencyAppWithoutExecutors(Session):
    compute: ClassVar[dict[str, object]] = {
        "preset": "latency",
        "switch_interval_ms": 1.0,
    }


class QtSummingApp(QtSession):
    summing: Annotated[AsPresenter[Summing], Declare()]


class SetupAsksApp(Session):
    asking: Annotated[AsPresenter[SetupAsks], Declare()]


class ProviderAsksApp(Session):
    providers: ClassVar[list[type]] = [ProviderAsks]


@pytest.fixture(autouse=True)
def eight_physical_cores(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend the machine has eight physical cores."""
    monkeypatch.setattr("redsun.session._base.physical_cores", lambda: 8)


def test_a_component_gets_a_working_executor(build: BuildSession) -> None:
    """Give a component an executor that runs calls on the session's pool."""
    session = build(SummingApp)
    assert session.summing.pool.submit(sum, [1, 2]).result(5) == 3


def test_two_components_get_different_executors(build: BuildSession) -> None:
    """Give each component an executor of its own over one pool."""
    session = build(TwoSummingApp)
    assert session.first.pool is not session.second.pool
    assert session.first.pool.submit(int, "4").result(5) == 4
    assert session.second.pool.submit(int, "5").result(5) == 5


@pytest.mark.parametrize("app", [SetupAsksApp, ProviderAsksApp])
def test_an_executor_outside_a_constructor_is_refused(
    build: BuildSession, app: type[Session]
) -> None:
    """Refuse an executor asked for in setup or by a provider, naming the parameter."""
    with pytest.raises(TypeError, match="'pool'.*constructor"):
        build(app)


def test_shutdown_cancels_queued_calls_and_restores_limits(
    build: BuildSession,
) -> None:
    """Cancel calls still queued and restore native limits and switch interval at shutdown."""
    before = threadpool_info()
    interval = sys.getswitchinterval()
    session = build(LatencyAppWithSumming)
    assert all(lib["num_threads"] == 7 for lib in threadpool_info())
    assert sys.getswitchinterval() == pytest.approx(0.001)
    blocker = threading.Event()
    session.summing.pool.submit(blocker.wait, 5)
    queued = session.summing.pool.submit(int)
    session.shutdown()
    blocker.set()
    assert queued.cancelled()
    assert threadpool_info() == before
    assert sys.getswitchinterval() == interval


def test_a_session_without_executors_leaves_the_limits(build: BuildSession) -> None:
    """Leave native limits and the switch interval alone when no component takes an executor."""
    before = threadpool_info()
    interval = sys.getswitchinterval()
    build(LatencyAppWithoutExecutors)
    assert threadpool_info() == before
    assert sys.getswitchinterval() == interval


def test_a_configured_executor_is_refused(build: BuildSession) -> None:
    """Refuse a session file filling a parameter the session gives an executor."""
    with pytest.raises(TypeError, match="'pool' keyword.*reserves for the session"):
        build(SummingApp, {"presenters": {"summing": {"pool": 2}}})


def test_a_long_wait_in_the_queue_is_logged(
    build: BuildSession,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Log a call that waited in the queue longer than the warning threshold."""
    monkeypatch.setattr("redsun.compute._executors.QUEUE_WAIT_WARNING", -1.0)
    session = build(SummingApp)
    session.summing.pool.submit(int).result(5)
    assert [r.name for r in caplog.records if "waited" in r.getMessage()] == [
        "redsun.compute.summing"
    ]


def test_the_summary_names_the_budget(
    build: BuildSession, caplog: pytest.LogCaptureFixture
) -> None:
    """Report the budget and the pool in the build summary."""
    with caplog.at_level(logging.INFO, logger="redsun"):
        build(SummingApp)
    assert "compute: balanced, 7 cores, 2 threads x 3 native" in caplog.text


@pytest.mark.qt
def test_a_qt_session_delivers_on_the_main_thread_until_it_shuts_down(
    qapp: QApplication, build: BuildSession, wait_until: Callable[..., bool]
) -> None:
    """Call a delivered result on the main thread, and drop one finishing after shutdown."""
    session = build(QtSummingApp)
    pool = session.summing.pool
    ran_on: list[threading.Thread] = []

    def record(value: object) -> None:
        ran_on.append(threading.current_thread())

    deliver(pool.submit(pow, 2, 3), record)
    assert wait_until(lambda: ran_on)
    assert ran_on == [threading.main_thread()]

    started, release, finished = threading.Event(), threading.Event(), threading.Event()

    def wait_for_release() -> bool:
        started.set()
        return release.wait(5)

    late = pool.submit(wait_for_release)
    deliver(late, record)
    late.add_done_callback(lambda _: finished.set())
    assert started.wait(5)
    session.shutdown()
    release.set()
    assert finished.wait(5)
    emit_queued()
    assert ran_on == [threading.main_thread()]
