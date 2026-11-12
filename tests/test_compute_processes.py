"""Tests of a process pool running calls in real worker processes."""

from __future__ import annotations

import os
import re
import sys
import threading
from typing import TYPE_CHECKING

import numpy as np
import pytest
from mock_pkg import compute_calls, compute_qt
from threadpoolctl import threadpool_info

from redsun import AsPresenter, Session
from redsun.compute import ProcessExecutor, ProcessPool, WorkerCrashed

if TYPE_CHECKING:
    from redsun.testing import BuildSession

pytestmark = [pytest.mark.processes, pytest.mark.usefixtures("launchable")]


class Computer:
    """Presenter taking a process executor in its constructor."""

    def __init__(self, name: str, executor: ProcessExecutor) -> None:
        self.name = name
        self.executor = executor


class Computes(Session):
    computer: AsPresenter[Computer]


def test_a_call_runs_in_a_worker() -> None:
    """Run a call in another process and return its result, arrays included."""
    with ProcessPool(1) as pool:
        assert pool.submit(compute_calls.pid).result(timeout=30) != os.getpid()
        array = np.arange(1 << 20, dtype=np.uint8)
        doubled = pool.submit(compute_calls.double, array).result(timeout=30)
        assert np.array_equal(doubled, array * 2)


def test_a_crashing_call_fails_alone(caplog: pytest.LogCaptureFixture) -> None:
    """Fail a call that kills its workers, log the exit code, and run another owner's call."""
    with ProcessPool(1) as pool:
        crash = ProcessExecutor(pool, "a").submit(compute_calls.crash, 3)
        assert isinstance(crash.exception(timeout=60), WorkerCrashed)
        added = ProcessExecutor(pool, "b").submit(compute_calls.add, 2, 3)
        assert added.result(timeout=30) == 5
    assert "exited with code 3" in caplog.text


def test_a_value_that_cannot_be_read_fails_only_its_call(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Fail a call whose argument or answer cannot be unpickled, and keep the worker."""
    with ProcessPool(1) as pool:
        sent = pool.submit(repr, compute_calls.Unmovable())
        assert isinstance(sent.exception(timeout=30), RuntimeError)
        answered = pool.submit(compute_calls.make_unmovable)
        with pytest.raises(TypeError, match="cannot be read in this process"):
            answered.result(timeout=30)
        assert pool.submit(compute_calls.add, 2, 3).result(timeout=30) == 5
    assert "exited with code" not in caplog.text
    assert caplog.text.count("' started") == 1


def test_an_answer_that_cannot_be_pickled_fails_only_its_call(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Fail a call whose result or error cannot be pickled, naming why, and keep the worker."""
    with ProcessPool(1) as pool:
        returned = pool.submit(compute_calls.make_lock)
        with pytest.raises(TypeError, match="returned a value that cannot be pickled"):
            returned.result(timeout=30)
        raised = pool.submit(compute_calls.raise_held_lock).exception(timeout=30)
        assert isinstance(raised, RuntimeError)
        assert str(raised).startswith("HeldLock: ")
        assert "Traceback in the worker process" in "".join(raised.__notes__)
        assert pool.submit(compute_calls.add, 2, 3).result(timeout=30) == 5
    assert "exited with code" not in caplog.text


def test_shutdown_stops_every_worker(caplog: pytest.LogCaptureFixture) -> None:
    """Stop each worker process at shutdown and log its exit."""
    pool = ProcessPool(2)
    pool.start()
    pool.shutdown()
    stopped = [
        record
        for record in caplog.records
        if re.match(r"Service 'worker-\d+' stopped with exit code", record.getMessage())
    ]
    assert len(stopped) == 2


@pytest.mark.skipif(sys.platform == "win32", reason="nice values are POSIX")
def test_a_refused_priority_warns_once_per_pool(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Warn once and run every worker at normal priority when high is refused."""

    def refuse(*args: object) -> None:
        raise PermissionError("not permitted")

    monkeypatch.setattr(os, "setpriority", refuse)
    with ProcessPool(2, priority="high") as pool:
        assert pool.submit(compute_calls.add, 1, 2).result(timeout=30) == 3
    assert caplog.text.count("runs at normal priority") == 1


def test_a_function_whose_module_loads_qt_is_named(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Warn once, naming the function, when its module loads Qt in the worker."""
    with ProcessPool(1) as pool:
        assert pool.submit(compute_qt.answer).result(timeout=30) == 42
        assert pool.submit(compute_qt.answer).result(timeout=30) == 42
    assert len(re.findall(r"answer imported [\w, ]*qtpy", caplog.text)) == 1


def test_a_component_gets_a_process_executor(build: BuildSession) -> None:
    """Hand a presenter a ProcessExecutor whose call runs in a worker once the session starts."""
    session = build(Computes)
    assert session.computer.executor.pool_type is ProcessPool
    future = session.computer.executor.submit(compute_calls.pid)
    assert future.result(timeout=30) != os.getpid()


def test_a_session_with_only_processes_leaves_its_own_limits(
    build: BuildSession,
) -> None:
    """Leave this process's native limits, switch interval and watchdog alone when only processes are asked for."""
    found = threadpool_info()
    interval = sys.getswitchinterval()
    build(Computes, {"compute": {"switch_interval_ms": 1}})
    assert threadpool_info() == found and sys.getswitchinterval() == interval
    assert [t for t in threading.enumerate() if t.name == "redsun-watchdog"] == []
