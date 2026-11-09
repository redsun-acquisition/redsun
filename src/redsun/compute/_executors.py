"""Executors that run computation off the calling thread."""

from __future__ import annotations

import asyncio
import weakref
from concurrent.futures import Executor, ThreadPoolExecutor
from typing import TYPE_CHECKING, ParamSpec, TypeVar, final

if TYPE_CHECKING:
    from collections.abc import Callable
    from concurrent.futures import Future

P = ParamSpec("P")
R = TypeVar("R")


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
        weakref.finalize(self, self._pool.shutdown, wait=False)

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
        return self._pool.submit(fn, *args, **kwargs)

    async def run(self, fn: Callable[P, R], /, *args: P.args, **kwargs: P.kwargs) -> R:
        """Run `fn(*args, **kwargs)` on the pool and await its result."""
        return await asyncio.wrap_future(self.submit(fn, *args, **kwargs))
