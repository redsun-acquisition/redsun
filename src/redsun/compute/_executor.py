"""The executor a component submits its calls through."""

from __future__ import annotations

import asyncio
import threading
import weakref
from concurrent.futures import Executor
from functools import partial
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Generic,
    ParamSpec,
    TypeVar,
    final,
    get_args,
)

from ._pool import Pool
from ._threads import ThreadPool

if TYPE_CHECKING:
    from collections.abc import Callable

    from ._future import Future
    from ._usage import OwnerUsage

P = ParamSpec("P")
R = TypeVar("R")
PoolT = TypeVar("PoolT", bound=Pool)


def set_event(event: threading.Event, _future: Future[Any]) -> None:
    """Set *event*, as a done-callback of a future."""
    event.set()


class PoolExecutor(Executor, Generic[PoolT]):
    """Submits one owner's calls to a pool several owners share.

    A subclass names its pool class as the type argument:
    `class MyExecutor(PoolExecutor[MyPool])`.
    """

    pool_type: ClassVar[type[Pool]]
    """The kind of pool this executor submits to."""

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)
        for base in cls.__dict__.get("__orig_bases__", ()):
            if getattr(base, "__origin__", None) is PoolExecutor:
                (cls.pool_type,) = get_args(base)
                return
        if not hasattr(cls, "pool_type"):
            raise TypeError(
                f"{cls.__name__} names no pool class: subclass PoolExecutor[...]"
            )

    def __init__(self, pool: PoolT, owner: str) -> None:
        self._pool = pool
        self._owner = owner
        self._lock = threading.Lock()
        self._futures: weakref.WeakSet[Future[Any]] = weakref.WeakSet()
        self._closed = False

    @property
    def native_threads(self) -> int:
        """Threads each worker's native libraries may use."""
        return self._pool.native_threads

    def _released(self) -> bool:
        return self._closed

    def submit(
        self, fn: Callable[P, R], /, *args: P.args, **kwargs: P.kwargs
    ) -> Future[R]:
        """Run `fn(*args, **kwargs)` on a worker of the pool.

        Raises
        ------
        RuntimeError
            If this executor has shut down.
        BrokenPool
            If the pool broke at start, or its workers broke.
        """
        if self._closed:
            raise RuntimeError("cannot schedule new futures after shutdown")
        future = self._pool._submit(self._owner, self._released, fn, args, kwargs)
        with self._lock:
            self._futures.add(future)
        return future

    async def run(self, fn: Callable[P, R], /, *args: P.args, **kwargs: P.kwargs) -> R:
        """Await the result of `fn(*args, **kwargs)` run on a worker."""
        return await asyncio.wrap_future(self.submit(fn, *args, **kwargs))

    def shutdown(self, wait: bool = True, *, cancel_futures: bool = False) -> None:
        """Refuse new calls, and cancel or wait for this owner's calls alone.

        The callbacks of calls still running are dropped. The pool keeps
        serving other owners. Calls still waiting for the pool to start are
        not waited for.
        """
        with self._lock:
            self._closed = True
            futures = list(self._futures)
        if cancel_futures:
            for future in futures:
                future.cancel()
        if wait:
            for future in futures:
                if not future._queued:
                    done = threading.Event()
                    future.add_done_callback(partial(set_event, done))
                    done.wait()

    def usage(self) -> OwnerUsage:
        """Return the counts of this owner's calls in the pool."""
        return self._pool._counts.of(self._owner)


@final
class ThreadExecutor(PoolExecutor[ThreadPool]):
    """Runs one owner's calls on a shared pool of threads."""
