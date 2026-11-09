from __future__ import annotations

import gc
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

import pytest

from redsun.compute import ThreadExecutor

if TYPE_CHECKING:
    from collections.abc import Callable, Generator


@pytest.fixture
def pool() -> Generator[ThreadPoolExecutor, None, None]:
    """Return a pool the test owns, shut down when it ends."""
    with ThreadPoolExecutor(1) as pool:
        yield pool


def compute_threads() -> list[threading.Thread]:
    """Return the live threads of the pools an executor builds."""
    return [t for t in threading.enumerate() if t.name.startswith("redsun-compute")]


def test_submit_returns_the_result() -> None:
    """Return a call's result through the future."""
    assert ThreadExecutor(2).submit(pow, 2, 10).result(timeout=5) == 1024


async def test_run_awaits_the_result() -> None:
    """Await a call's result."""
    assert await ThreadExecutor(1).run(pow, 3, 2) == 9


def test_an_own_pool_stops_when_the_executor_is_freed(
    wait_until: Callable[..., bool],
) -> None:
    """Stop the pool an executor built when the executor is freed."""
    executor = ThreadExecutor(1)
    executor.submit(int).result(timeout=5)
    assert compute_threads()
    del executor
    gc.collect()
    assert wait_until(lambda: not compute_threads(), timeout=5)


def test_a_given_pool_outlives_the_executor(pool: ThreadPoolExecutor) -> None:
    """Leave a pool the executor did not build running when it is freed."""
    executor = ThreadExecutor._from_pool(pool, 4, "owner")
    assert executor.native_threads == 4
    del executor
    gc.collect()
    assert pool.submit(pow, 2, 3).result(timeout=5) == 8
