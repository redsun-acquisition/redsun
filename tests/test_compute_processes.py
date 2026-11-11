"""Tests of a process pool running calls in real worker processes."""

from __future__ import annotations

import os
import re
import sys
from typing import final

import numpy as np
import pytest
from mock_pkg import compute_calls, compute_qt

from redsun.compute import ProcessPool, WorkerCrashed
from redsun.compute._pool import PoolExecutor

pytestmark = [pytest.mark.processes, pytest.mark.usefixtures("launchable")]


@final
class OwnerExecutor(PoolExecutor[ProcessPool]):
    """Submits one owner's calls to a process pool."""


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
        crash = OwnerExecutor(pool, "a").submit(compute_calls.crash, 3)
        assert isinstance(crash.exception(timeout=60), WorkerCrashed)
        added = OwnerExecutor(pool, "b").submit(compute_calls.add, 2, 3)
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
