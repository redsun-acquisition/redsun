"""A session hands its components executors and starts the pools behind them."""

from __future__ import annotations

import logging
import sys
import threading
from typing import TYPE_CHECKING, Annotated

import bluesky.plan_stubs as bps
import numpy as np
import pytest
from bluesky.utils import MsgGenerator
from ophyd_async.core import StandardReadable, soft_signal_rw
from threadpoolctl import threadpool_info

from docs.examples.background_processing import MedianPresenter
from redsun import (
    AsDevice,
    AsPresenter,
    Declare,
    RegistrationError,
    Session,
    provides,
)
from redsun.compute import (
    Future,
    ProcessExecutor,
    ProcessPool,
    ProcessPoolSettings,
    ThreadExecutor,
    ThreadPool,
    ThreadPoolSettings,
)
from redsun.compute._future import PRE_START
from redsun.presenter import AcquisitionPresenter
from redsun.qt import QtSession

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from numpy.typing import NDArray
    from qtpy.QtWidgets import QApplication

    from redsun import PlanEntry
    from redsun.testing import BuildSession


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


class Fitter:
    """Presenter asking for a process executor in its constructor, never submitting."""

    def __init__(self, name: str, executor: ProcessExecutor) -> None:
        self.name = name


class SetupFitter:
    """Presenter asking for a process executor in its `setup` only."""

    def __init__(self, name: str) -> None:
        self.name = name

    def setup(self, executor: ProcessExecutor) -> None:
        pass


class FailingFitter:
    """Presenter failing to build after asking for a process executor."""

    def __init__(self, name: str, executor: ProcessExecutor) -> None:
        raise RuntimeError("no fit today")


class OwnWorkers:
    """Presenter taking a `workers` keyword of its own and a process executor."""

    def __init__(self, name: str, workers: int, executor: ProcessExecutor) -> None:
        self.name = name


class ThreadWorkers:
    """Presenter taking a `workers` keyword of its own and no process executor."""

    def __init__(self, name: str, workers: int) -> None:
        self.name = name
        self.workers = workers


class WorkerCamera(StandardReadable):
    """Device taking a `workers` keyword of its own."""

    def __init__(self, workers: int, name: str = "") -> None:
        self.workers = workers
        super().__init__(name=name)


class FrameCamera(StandardReadable):
    """Camera whose frame a plan sets before each reading."""

    def __init__(self, name: str = "") -> None:
        with self.add_children_as_readables():
            self.frame = soft_signal_rw(np.ndarray, np.zeros((4, 4)))
        super().__init__(name=name)


class FramePlans:
    """Offers a run of three frames of 1, 2 and 9."""

    def __init__(self, name: str) -> None:
        self.name = name

    def plan_map(self) -> Mapping[str, PlanEntry]:
        """Return the plan offered."""
        return {"frames": {"plan": self.frames}}

    def frames(self, camera: FrameCamera) -> MsgGenerator[None]:
        """Read *camera* once per frame value, in one run."""
        yield from bps.open_run()
        for value in (1, 2, 9):
            yield from bps.mv(camera.frame, np.full((4, 4), value))
            yield from bps.trigger_and_read([camera])
        yield from bps.close_run()


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


class TwoFitters(Session):
    fit_a: AsPresenter[Fitter]
    fit_b: AsPresenter[Fitter]


class OneFitter(Session):
    fit: AsPresenter[Fitter]


class FitterWithSetupFitter(Session):
    fit: AsPresenter[Fitter]
    later: AsPresenter[SetupFitter]


class ThreadsWithWorkers(Session):
    median: AsPresenter[Median]


class OwnWorkersLab(Session):
    own: AsPresenter[OwnWorkers]


class ThreadWorkersLab(Session):
    own: AsPresenter[ThreadWorkers]


class FitterAndCamera(Session):
    fit: AsPresenter[Fitter]
    camera: AsDevice[WorkerCamera]


class FitterFailsAfterAsking(Session):
    fails: AsPresenter[FailingFitter]
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


class MedianLab(QtSession):
    camera: AsDevice[FrameCamera]
    plans: AsPresenter[FramePlans]
    acquisition: AsPresenter[AcquisitionPresenter]
    median: Annotated[AsPresenter[MedianPresenter], Declare(source="camera-frame")]


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
    """Make no pool, start no watchdog, and leave native limits and the switch interval as found."""

    def unread() -> int:
        raise AssertionError("the physical cores were read")

    monkeypatch.setattr("redsun.session._compute.physical_cores", unread)
    found = threadpool_info()
    interval = sys.getswitchinterval()
    session = build(NoCompute, {"compute": {"switch_interval_ms": 1}})
    assert session.pool_settings == {}
    assert threadpool_info() == found and sys.getswitchinterval() == interval
    assert watchdog_threads() == []


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
    """Run one watchdog thread and the switch interval while a pool runs, and restore both at shutdown."""
    interval = sys.getswitchinterval()
    session = build(OneMedian, {"compute": {"switch_interval_ms": 1}})
    assert len(watchdog_threads()) == 1
    assert sys.getswitchinterval() == 0.001
    session.shutdown()
    assert watchdog_threads() == []
    assert sys.getswitchinterval() == interval


@pytest.mark.qt
def test_a_run_s_documents_reach_a_presenter_that_computes_in_the_pool(
    qapp: QApplication,
    build: BuildSession,
    monkeypatch: pytest.MonkeyPatch,
    wait_until: Callable[..., bool],
) -> None:
    """Compute the median of a run's frames on a pool thread and publish it on the main thread."""
    computed_on: list[str] = []

    def median_of(frames: list[NDArray[np.uint16]]) -> NDArray[np.float64]:
        computed_on.append(threading.current_thread().name)
        return np.median(np.stack(frames), axis=0)

    monkeypatch.setattr("docs.examples.background_processing.median_of", median_of)
    session = build(MedianLab, {"mock": True})
    published: list[tuple[NDArray[np.float64], str]] = []
    session.median.sig_median.connect(
        lambda m: published.append((m, threading.current_thread().name))
    )

    session.acquisition.launch("frames", {"camera": "camera"}, ["median"])

    assert wait_until(lambda: bool(published))
    median, published_on = published[-1]
    assert np.array_equal(median, np.full((4, 4), 2))
    assert published_on == threading.main_thread().name
    assert threading.main_thread().name not in computed_on


@pytest.fixture
def eight_cores(monkeypatch: pytest.MonkeyPatch) -> None:
    """Report eight physical cores to the session."""
    monkeypatch.setattr("redsun.session._compute.physical_cores", lambda: 8)


@pytest.mark.usefixtures("eight_cores")
def test_each_component_gets_its_own_process_pool(
    build: BuildSession, caplog: pytest.LogCaptureFixture
) -> None:
    """Report one ProcessPool per component, sized by the share of the compute cores."""
    caplog.set_level(logging.INFO, logger="redsun")
    session = build(TwoFitters, {"compute": {"cores": 4}})
    assert session.pool_settings[ProcessPool, "fit_a"] == ProcessPoolSettings(2)
    assert session.pool_settings[ProcessPool, "fit_b"] == ProcessPoolSettings(2)
    assert "ProcessPool of fit_a: 2 processes, priority normal" in caplog.text
    assert "ProcessPool of fit_b: 2 processes, priority normal" in caplog.text


@pytest.mark.usefixtures("eight_cores")
def test_a_setup_asking_for_processes_counts_for_the_share(build: BuildSession) -> None:
    """Divide the compute cores between the components asking in a constructor or in a setup."""
    session = build(FitterWithSetupFitter, {"compute": {"cores": 4}})
    assert session.pool_settings[ProcessPool, "fit"] == ProcessPoolSettings(2)
    assert session.pool_settings[ProcessPool, "later"] == ProcessPoolSettings(2)


@pytest.mark.usefixtures("eight_cores")
@pytest.mark.parametrize(
    ("entry", "section", "expected"),
    [({"workers": 3}, {"processes": 2}, 3), ({}, {"processes": 2}, 2), ({}, {}, 4)],
)
def test_the_worker_count_comes_from_the_entry_then_the_section_then_the_share(
    build: BuildSession,
    entry: dict[str, object],
    section: dict[str, object],
    expected: int,
) -> None:
    """Take the entry's workers, else compute.processes, else the session's share."""
    session = build(
        OneFitter,
        {"presenters": {"fit": entry}, "compute": {"cores": 4, **section}},
    )
    assert session.pool_settings[ProcessPool, "fit"] == ProcessPoolSettings(expected)


@pytest.mark.usefixtures("eight_cores")
def test_the_priority_of_the_section_reaches_every_process_pool(
    build: BuildSession,
) -> None:
    """Give each process pool the priority the compute section names."""
    session = build(TwoFitters, {"compute": {"cores": 4, "priority": "low"}})
    for owner in ("fit_a", "fit_b"):
        assert session.pool_settings[ProcessPool, owner] == ProcessPoolSettings(
            2, priority="low"
        )


@pytest.mark.usefixtures("eight_cores")
def test_more_workers_than_cores_are_warned_and_kept(
    build: BuildSession, caplog: pytest.LogCaptureFixture
) -> None:
    """Warn once when the pools ask for more workers than the compute cores, and keep them."""
    with caplog.at_level(logging.WARNING, logger="redsun"):
        session = build(
            OneFitter,
            {"presenters": {"fit": {"workers": 9}}, "compute": {"cores": 4}},
        )
    assert session.pool_settings[ProcessPool, "fit"] == ProcessPoolSettings(9)
    warning = "Process pools have 9 workers in all, more than the 4 compute cores"
    assert caplog.text.count(warning) == 1


def test_workers_without_a_process_executor_are_ignored_with_a_warning(
    build: BuildSession, caplog: pytest.LogCaptureFixture
) -> None:
    """Warn that workers is ignored for a component asking for no ProcessExecutor."""
    with caplog.at_level(logging.WARNING, logger="redsun"):
        session = build(ThreadsWithWorkers, {"presenters": {"median": {"workers": 2}}})
    assert "median" in session.presenters
    assert "median gives 'workers' but asks for no ProcessExecutor; ignored" in (
        caplog.text
    )


def test_workers_with_no_executor_asked_for_are_ignored_with_a_warning(
    build: BuildSession, caplog: pytest.LogCaptureFixture
) -> None:
    """Warn that workers is ignored in a session whose components ask for no executor."""
    with caplog.at_level(logging.WARNING, logger="redsun"):
        session = build(NoCompute, {"presenters": {"plain": {"workers": 2}}})
    assert "plain" in session.presenters
    assert "plain gives 'workers' but asks for no ProcessExecutor; ignored" in (
        caplog.text
    )


@pytest.mark.usefixtures("eight_cores")
def test_a_process_pool_of_a_failed_component_never_starts(
    build: BuildSession, caplog: pytest.LogCaptureFixture
) -> None:
    """Skip a component that fails after asking for a ProcessExecutor, and shut down cleanly."""
    with caplog.at_level(logging.ERROR, logger="redsun"):
        session = build(FitterFailsAfterAsking)
    assert "fails" not in session.presenters
    assert "plain" in session.presenters
    assert "no fit today" in caplog.text
    session.shutdown()


def test_workers_reach_the_constructor_of_a_device_or_a_class_without_processes(
    build: BuildSession,
) -> None:
    """Pass workers to a device, and to a presenter taking it and asking for no ProcessExecutor."""
    session = build(FitterAndCamera, {"devices": {"camera": {"workers": 2}}})
    assert session.camera.workers == 2
    assert (
        build(ThreadWorkersLab, {"presenters": {"own": {"workers": 3}}}).own.workers
        == 3
    )


@pytest.mark.parametrize("workers", [0, -1, True, 1.5, "2"])
def test_a_workers_that_is_not_a_whole_number_of_one_or_more_skips_the_component(
    build: BuildSession, caplog: pytest.LogCaptureFixture, workers: object
) -> None:
    """Skip a presenter whose workers is not an int of at least 1, naming the key."""
    with caplog.at_level(logging.ERROR, logger="redsun"):
        session = build(OneFitter, {"presenters": {"fit": {"workers": workers}}})
    assert "fit" not in session.presenters
    assert f"gives workers={workers!r}" in caplog.text


def test_a_class_taking_workers_itself_is_skipped(
    build: BuildSession, caplog: pytest.LogCaptureFixture
) -> None:
    """Skip a presenter taking workers and a ProcessExecutor when the declaration gives workers."""
    with caplog.at_level(logging.ERROR, logger="redsun"):
        session = build(OwnWorkersLab, {"presenters": {"own": {"workers": 2}}})
    assert "own" not in session.presenters
    assert "takes a 'workers' keyword of its own and asks for a ProcessExecutor" in (
        caplog.text
    )
