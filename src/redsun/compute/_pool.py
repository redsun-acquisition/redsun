"""The lifecycle every pool shares, and the executor that submits to one."""

from __future__ import annotations

import asyncio
import enum
import logging
import threading
import time
import weakref
from abc import ABC, abstractmethod
from collections import deque
from concurrent.futures import Executor
from dataclasses import dataclass
from functools import partial
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    ClassVar,
    Final,
    Generic,
    ParamSpec,
    TypeVar,
    get_args,
)

from diwire import Component

from ._future import BrokenPool, Future, trace
from ._usage import POOL_OWNER, Counts, listed

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from typing import Self

    from ._future import Delivery
    from ._usage import OwnerUsage

P = ParamSpec("P")
R = TypeVar("R")
PoolT = TypeVar("PoolT", bound="Pool")

LONG_WAIT: Final = 1.0

logger = logging.getLogger("redsun")


class State(enum.Enum):
    """Where a pool is in its life."""

    MADE = enum.auto()
    STARTED = enum.auto()
    BROKEN = enum.auto()
    SHUT_DOWN = enum.auto()


def never_released() -> bool:
    """Report that the owner of a call is still there."""
    return False


def pool_key(kind: type[Pool], group: str | None) -> object:
    """Return the registry key of the pool of *kind* that serves *group*."""
    return kind if group is None else Annotated[kind, Component(group)]


@dataclass(slots=True, eq=False)
class Call(Generic[R]):
    """A call a pool holds until a worker runs it."""

    owner: str
    fn: Callable[..., R]
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    future: Future[R]
    submitted: float
    """Monotonic time the call started waiting."""

    counts: Counts

    def run(
        self,
        through: Callable[[Callable[..., R], tuple[Any, ...], dict[str, Any]], R]
        | None = None,
    ) -> None:
        """Run the call in this thread and settle its future.

        With *through*, the result is `through(fn, args, kwargs)`, so the
        function may run elsewhere and is left out of the list of functions
        this process's pool threads are running.

        The call lets go of its future when it starts, and the failing branch
        drops the local too: the exception's traceback reaches this frame and
        the caller's, so any reference to the future from there would keep it
        alive in a cycle.
        """
        future = self.future
        if not future.set_running_or_notify_cancel():
            return
        del self.future
        waited = time.monotonic() - self.submitted
        self.counts.started(self.owner, waited)
        if waited > LONG_WAIT:
            logger.warning(f"A call of {self.owner} waited {waited:.1f} s for a worker")
        try:
            if through is None:
                result = self.invoke()
            else:
                result = through(self.fn, self.args, self.kwargs)
        except BaseException as error:  # noqa: BLE001 - the future carries it to the caller
            self.counts.finished(self.owner, failed=True)
            future.set_exception(error)
            del future
        else:
            self.counts.finished(self.owner, failed=False)
            future.set_result(result)

    def invoke(self) -> R:
        """Return what the function returns, listing it as running meanwhile."""
        with listed(self.fn):
            return self.fn(*self.args, **self.kwargs)

    def cancel(self) -> None:
        """Cancel a call that never ran, and release those waiting on its future."""
        if self.future.cancel():
            self.future.set_running_or_notify_cancel()

    def fail(self, error: BaseException) -> None:
        """Settle a call that never ran with *error*."""
        if self.future.set_running_or_notify_cancel():
            self.counts.started(self.owner, 0.0)
            self.counts.finished(self.owner, failed=True)
            self.future.set_exception(error)


def drop_if_cancelled(counts: Counts, owner: str, future: Future[Any]) -> None:
    """Count a call cancelled before it ran as no longer waiting."""
    if future.cancelled():
        counts.dropped(owner)


class Pool(Executor, ABC):
    """Workers that run calls, with the lifecycle every kind shares.

    A pool is made, started once, and shut down. Calls submitted before
    `start` wait and run first, in order. A kind writes `_start`, `_dispatch`
    and `_stop`; `_stop` must tolerate a pool that never started and a second
    call.
    """

    def __init__(self, *, native_threads: int = 1) -> None:
        self._native_threads = native_threads
        self._counts = Counts()
        self._lock = threading.RLock()
        self._waiting: deque[Call[Any]] = deque()
        self._state = State.MADE
        self._broken = ""
        self._delivery: Delivery | None = None
        self._label = "Pool"

    @classmethod
    @abstractmethod
    def resource(cls, *args: Any, **kwargs: Any) -> Generator[Self, None, None]:
        """Build a pool, yield it unstarted, and stop it at teardown."""

    @property
    def native_threads(self) -> int:
        """Threads each worker's native libraries may use."""
        return self._native_threads

    @property
    @abstractmethod
    def pool_size(self) -> int:
        """Threads, processes or devices."""

    def _start(self) -> None:
        """Make the workers."""

    @abstractmethod
    def _dispatch(self, call: Call[Any]) -> None:
        """Hand *call* to a worker."""

    @abstractmethod
    def _stop(self, wait: bool, cancel_futures: bool) -> None:
        """Stop the workers."""

    def start(self) -> None:
        """Make the workers and send the waiting calls, once.

        Raises
        ------
        BrokenPool
            If the workers cannot be made. The waiting calls fail with it too.
        """
        with self._lock:
            if self._state is not State.MADE:
                return
            try:
                self._start()
            except Exception as error:
                logger.error(f"{self._label} did not start: {trace(error)}")
                self._break(f"the pool did not start: {error}", log=False)
                raise BrokenPool(self._broken) from error
            try:
                while self._waiting:
                    call = self._waiting.popleft()
                    call.future._mark_queued(False)
                    call.submitted = time.monotonic()
                    try:
                        self._dispatch(call)
                    except Exception as error:  # noqa: BLE001 - the call's future carries it
                        logger.error(f"A waiting call could not start: {trace(error)}")
                        call.fail(error.with_traceback(None))
            finally:
                self._state = State.STARTED

    def _check(self, fn: Callable[..., Any]) -> None:
        """Raise before anything is queued if the pool cannot run *fn*."""

    def _break(self, reason: str, *, log: bool = True) -> None:
        """Mark the pool broken and fail the calls waiting for it, logging *reason* unless *log* is false."""
        with self._lock:
            self._state = State.BROKEN
            self._broken = reason
            if log:
                logger.error(f"{self._label} is broken: {reason}")
            while self._waiting:
                self._waiting.popleft().fail(BrokenPool(reason))

    def _submit(
        self,
        owner: str,
        released: Callable[[], bool],
        fn: Callable[..., R],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Future[R]:
        """Run `fn(*args, **kwargs)` on a worker, counted under *owner*, binding *released* to the future.

        A call made before `start` waits for it.

        Raises
        ------
        BrokenPool
            If the pool did not start.
        RuntimeError
            If the pool has shut down.
        """
        self._check(fn)
        future: Future[R] = Future()
        future._bind(owner, self._delivery, released)
        call = Call(owner, fn, args, kwargs, future, time.monotonic(), self._counts)
        with self._lock:
            match self._state:
                case State.BROKEN:
                    raise BrokenPool(self._broken)
                case State.SHUT_DOWN:
                    raise RuntimeError("cannot schedule new futures after shutdown")
                case State.MADE:
                    future._mark_queued(True)
                    self._waiting.append(call)
                    send = False
                case State.STARTED:
                    send = True
            self._counts.submitted(owner)
            future.add_done_callback(partial(drop_if_cancelled, self._counts, owner))
        if send:
            try:
                self._dispatch(call)
            except Exception:
                future.cancel()
                raise
        return future

    def submit(
        self, fn: Callable[P, R], /, *args: P.args, **kwargs: P.kwargs
    ) -> Future[R]:
        """Run `fn(*args, **kwargs)` on a worker, counted under `"<pool>"`."""
        return self._submit(POOL_OWNER, never_released, fn, args, kwargs)

    def shutdown(self, wait: bool = True, *, cancel_futures: bool = False) -> None:
        """Cancel the calls waiting for `start`, then stop the workers."""
        with self._lock:
            if self._state is not State.BROKEN:
                self._state = State.SHUT_DOWN
            waiting = list(self._waiting)
            self._waiting.clear()
        for call in waiting:
            call.cancel()
        self._stop(wait, cancel_futures)

    def __enter__(self) -> Self:
        """Start the pool."""
        self.start()
        return self


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
        TypeError
            If the pool runs calls in worker processes and *fn* is one a worker
            cannot import: a lambda, a closure, a bound method or a function
            defined in the script being run.
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
