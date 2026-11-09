"""Executors that run computation off the calling thread."""

from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import Executor, ThreadPoolExecutor
from functools import partial
from typing import TYPE_CHECKING, Final, ParamSpec, TypeVar, final

if TYPE_CHECKING:
    from collections.abc import Callable
    from concurrent.futures import Future

P = ParamSpec("P")
R = TypeVar("R")

QUEUE_WAIT_WARNING: Final = 1.0
"""Seconds a call of a session's executor may wait for a worker before it is logged."""


def timed(owner: str, queued: float, call: partial[R]) -> R:
    """Run *call*, logging under *owner* when it waited too long since *queued*."""
    waited = time.perf_counter() - queued
    if waited > QUEUE_WAIT_WARNING:
        name = getattr(call.func, "__qualname__", call.func)
        logging.getLogger(f"redsun.compute.{owner}").warning(
            "%s waited %.2f s for a worker", name, waited
        )
    return call()


@final
class ThreadExecutor:
    """Run calls on a pool of threads.

    Parameters
    ----------
    threads
        Number of calls that run at the same time.
    native_threads
        Threads each call may use inside native code, such as a BLAS
        routine. It is a figure to read, not a limit this class enforces.
    """

    __slots__ = ("__weakref__", "_native_threads", "_owner", "_pool")

    def __init__(self, threads: int = 1, *, native_threads: int = 1) -> None:
        self._pool: Executor = ThreadPoolExecutor(
            threads, thread_name_prefix="redsun-compute"
        )
        self._native_threads = native_threads
        self._owner: str | None = None

    @classmethod
    def _from_pool(
        cls, pool: Executor, native_threads: int, owner: str
    ) -> ThreadExecutor:
        """Return an executor over *pool*, which it never shuts down."""
        self = cls.__new__(cls)
        self._pool = pool
        self._native_threads = native_threads
        self._owner = owner
        return self

    @property
    def native_threads(self) -> int:
        """Threads each call may use inside native code."""
        return self._native_threads

    def __repr__(self) -> str:
        owner = "" if self._owner is None else f", owner={self._owner!r}"
        return f"ThreadExecutor(native_threads={self._native_threads}{owner})"

    def submit(
        self, fn: Callable[P, R], /, *args: P.args, **kwargs: P.kwargs
    ) -> Future[R]:
        """Schedule `fn(*args, **kwargs)` and return its future."""
        if self._owner is None:
            return self._pool.submit(fn, *args, **kwargs)
        call = partial(fn, *args, **kwargs)
        return self._pool.submit(timed, self._owner, time.perf_counter(), call)

    async def run(self, fn: Callable[P, R], /, *args: P.args, **kwargs: P.kwargs) -> R:
        """Run `fn(*args, **kwargs)` on the pool and await its result."""
        return await asyncio.wrap_future(self.submit(fn, *args, **kwargs))
