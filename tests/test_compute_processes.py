"""A session gives each component asking for a ProcessExecutor a pool of its own."""

from __future__ import annotations

import subprocess
import sys
import threading
from typing import TYPE_CHECKING

import pytest
from mock_pkg.compute_calls import add, crash, log_warning, spin_for
from threadpoolctl import threadpool_info

from redsun import AsPresenter, Session
from redsun.compute import ProcessExecutor, WorkerCrashed
from redsun.log import log_buffer
from tests.sdk.helpers import kept_under

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from redsun.testing import BuildSession

pytestmark = pytest.mark.processes

UNGUARDED = """
from redsun import AsPresenter, Session
from redsun.compute import ProcessExecutor, WorkerCrashed


class Fitter:
    def __init__(self, name, executor: ProcessExecutor):
        print("built", flush=True)
        self.name = name
        self.executor = executor


class Lab(Session):
    fit: AsPresenter[Fitter]


session = Lab({"compute": {"processes": 1}}).build()
try:
    session.fit.executor.submit(pow, 2, 3).result(timeout=60)
except WorkerCrashed:
    print("crashed", flush=True)
finally:
    session.shutdown()
"""


class Computer:
    """Presenter handing its process executor to the test."""

    def __init__(self, name: str, executor: ProcessExecutor) -> None:
        self.name = name
        self.executor = executor


class LastWord:
    """Presenter submitting one more call, and waiting for it, as it shuts down."""

    def __init__(self, name: str, executor: ProcessExecutor) -> None:
        self.name = name
        self.executor = executor
        self.last: int | None = None

    def shutdown(self) -> None:
        self.last = self.executor.submit(add, 1, 2).result(timeout=30)


class TwoComputers(Session):
    crashing: AsPresenter[Computer]
    steady: AsPresenter[Computer]


class OneComputer(Session):
    fit: AsPresenter[Computer]


class ShutsDownLast(Session):
    last: AsPresenter[LastWord]


def watchdog_threads() -> list[threading.Thread]:
    """Return the watchdog threads alive."""
    return [t for t in threading.enumerate() if t.name == "redsun-watchdog"]


def test_a_crash_fails_only_its_own_component(build: BuildSession) -> None:
    """Fail the crashing component's call and return the other component's."""
    session = build(TwoComputers, {"compute": {"processes": 1}})
    steady = session.steady.executor.submit(spin_for, 3.0)
    crashing = session.crashing.executor.submit(crash, 3)
    with pytest.raises(WorkerCrashed):
        crashing.result(timeout=30)
    assert steady.result(timeout=30) is None


def test_a_session_with_only_processes_leaves_its_own_limits(
    build: BuildSession,
) -> None:
    """Start no watchdog and change no native limit when only process pools run."""
    found = threadpool_info()
    interval = sys.getswitchinterval()
    session = build(OneComputer, {"compute": {"processes": 1, "switch_interval_ms": 1}})
    assert session.fit.executor.submit(add, 1, 2).result(timeout=30) == 3
    assert watchdog_threads() == []
    assert threadpool_info() == found
    assert sys.getswitchinterval() == interval


def test_worker_records_reach_the_log_buffer_as_their_own_source(
    build: BuildSession, wait_until: Callable[..., bool]
) -> None:
    """Show a worker's warning in the buffer under workers.<component>."""
    session = build(OneComputer, {"compute": {"processes": 1}})
    session.fit.executor.submit(log_warning, "fit is slow").result(timeout=30)
    assert wait_until(
        lambda: (
            "fit is slow"
            in [r.getMessage() for r in log_buffer().service_records("workers.fit")]
        )
    )


def test_the_pool_stops_after_the_component(build: BuildSession) -> None:
    """Let a component's shutdown submit a last call that still returns."""
    session = build(ShutsDownLast, {"compute": {"processes": 1}})
    component = session.last
    session.shutdown()
    assert component.last == 3


def test_an_unguarded_script_builds_its_session_once(tmp_path: Path) -> None:
    """Refuse the build a worker starts by running an unguarded script, and fail the call."""
    script = tmp_path / "unguarded.py"
    script.write_text(kept_under(tmp_path) + UNGUARDED, encoding="utf-8")
    ran = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        cwd=tmp_path,
    )

    assert ran.returncode == 0, ran.stderr
    printed = [line for line in ran.stdout.splitlines() if line in ("built", "crashed")]
    assert printed == ["built", "crashed"]
    assert "RuntimeError: Session.build ran inside a worker process" in ran.stderr
