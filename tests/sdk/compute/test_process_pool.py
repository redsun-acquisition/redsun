"""Tests for the process pool, run inline."""

from __future__ import annotations

import pytest
from mock_pkg.compute_calls import add, make_lock

from redsun.compute import ProcessExecutor, ProcessPool


def test_an_inline_pool_returns_the_result() -> None:
    """Return a call's result from a ProcessPool(0) after a pickling round trip."""
    with ProcessPool(0) as pool:
        assert pool.submit(add, 2, 3).result() == 5


def test_a_lambda_is_refused_at_submit() -> None:
    """Refuse a lambda with TypeError before anything is queued."""
    with ProcessPool(0) as pool:
        executor = ProcessExecutor(pool, "owner")
        with pytest.raises(TypeError, match="module level"):
            executor.submit(lambda: 1)
        assert executor.usage().queued == 0


def test_inline_processes_catches_an_unpicklable_argument(
    inline_processes: ProcessExecutor,
) -> None:
    """Fail a call whose argument holds a lock, naming the argument."""
    future = inline_processes.submit(add, make_lock(), 1)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match=r"add\(a=\.\.\.\)"):
        future.result()
