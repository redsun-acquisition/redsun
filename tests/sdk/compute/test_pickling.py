"""Tests for the checks on what a process pool is sent."""

from __future__ import annotations

import threading
from collections import Counter
from functools import partial
from typing import TYPE_CHECKING

import pytest

from redsun.compute import ProcessPool

if TYPE_CHECKING:
    from collections.abc import Callable


def add(a: int, b: int) -> int:
    """Return the sum, as a call a worker can run."""
    return a + b


def fit(trace: object) -> None:
    """Take an argument and return nothing."""


def make_lock() -> object:
    """Return a value that cannot be pickled."""
    return threading.Lock()


def test_a_lambda_is_refused_before_anything_starts() -> None:
    """Refuse a lambda, a closure and a bound method at submit, before the pool starts."""
    pool = ProcessPool(0)

    def local() -> int:
        return 1

    refused: tuple[Callable[..., object], ...] = (
        lambda: 1,
        local,
        Counter().most_common,
        partial(local),
    )
    for fn in refused:
        with pytest.raises(TypeError, match="send a function defined at module level"):
            pool.submit(fn)
    pool.shutdown()


def test_a_function_from_the_script_being_run_is_refused() -> None:
    """Refuse a function defined in `__main__`, plain or inside a partial."""
    pool = ProcessPool(0)

    def in_script() -> int:
        return 1

    in_script.__qualname__ = "in_script"
    in_script.__module__ = "__main__"
    for fn in (in_script, partial(in_script)):
        with pytest.raises(TypeError, match="script being run"):
            pool.submit(fn)
    pool.shutdown()


def test_the_argument_at_fault_is_named() -> None:
    """Fail the call with a TypeError naming the argument that cannot be pickled."""
    with ProcessPool(0) as pool:
        error = pool.submit(fit, trace=threading.Lock()).exception(timeout=1)
    assert isinstance(error, TypeError)
    assert str(error).startswith("fit(trace=...): ")


def test_a_positional_argument_is_named_by_its_parameter() -> None:
    """Name the parameter of a positional argument that cannot be pickled."""
    with ProcessPool(0) as pool:
        error = pool.submit(fit, threading.Lock()).exception(timeout=1)
    assert str(error).startswith("fit(trace=...): ")


def test_inline_round_trip_catches_an_unpicklable_result() -> None:
    """Fail the call when its result cannot be pickled, naming the function."""
    with ProcessPool(0) as pool:
        error = pool.submit(make_lock).exception(timeout=1)
    assert "make_lock() returned a value that cannot be pickled" in str(error)


def test_inline_round_trip_returns_the_result() -> None:
    """Return the result of a call run inline through a pickle round trip."""
    with ProcessPool(0) as pool:
        assert pool.submit(add, 2, b=3).result(timeout=1) == 5


def test_an_unpicklable_argument_before_start_fails_alone() -> None:
    """Fail only the call whose argument cannot be pickled when a pool that queued it starts."""
    pool = ProcessPool(0)
    bad = pool.submit(fit, threading.Lock())
    good = pool.submit(add, 2, 3)
    pool.start()
    assert isinstance(bad.exception(timeout=1), TypeError)
    assert good.result(timeout=1) == 5
    pool.shutdown()
