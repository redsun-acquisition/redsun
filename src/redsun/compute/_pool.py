"""The lifecycle every pool shares."""

from __future__ import annotations

import enum
import logging
import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from concurrent.futures import Executor
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Annotated, Any, Final, Generic, ParamSpec, TypeVar

from diwire import Component

from ._future import BrokenPool, Future, logger, trace
from ._usage import POOL_OWNER, Counts

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from typing import Self

    from ._future import Delivery
    from ._usage import Usage

P = ParamSpec("P")
R = TypeVar("R")

LONG_WAIT: Final = 1.0


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

    def run(self) -> None:
        """Run the call in this thread and settle its future.

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
            logging.getLogger(f"redsun.compute.{self.owner}").warning(
                f"A call waited {waited:.1f} s for a worker"
            )
        try:
            result = self.fn(*self.args, **self.kwargs)
        except BaseException as error:  # noqa: BLE001 - the future carries it to the caller
            self.counts.finished(self.owner, failed=True)
            future.set_exception(error)
            del future
        else:
            self.counts.finished(self.owner, failed=False)
            future.set_result(result)

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

    @classmethod
    def resource(cls, *args: Any, **kwargs: Any) -> Generator[Self, None, None]:
        """Build a pool, yield it unstarted, and stop it at teardown."""
        raise NotImplementedError

    @property
    def native_threads(self) -> int:
        """Threads each worker's native libraries may use."""
        return self._native_threads

    @property
    @abstractmethod
    def pool_size(self) -> int:
        """Threads, processes or devices."""

    @property
    def delivery(self) -> Delivery | None:
        """Where callbacks of this pool's futures run, if the session set it."""
        return self._delivery

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
                self._state = State.BROKEN
                self._broken = f"the pool did not start: {error}"
                logger.error(f"Pool did not start: {trace(error)}")
                while self._waiting:
                    self._waiting.popleft().fail(BrokenPool(self._broken))
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

    def submit_as(
        self, owner: str, fn: Callable[P, R], /, *args: P.args, **kwargs: P.kwargs
    ) -> Future[R]:
        """Run `fn(*args, **kwargs)` on a worker, counted under *owner*.

        A call made before `start` waits for it.

        Raises
        ------
        BrokenPool
            If the pool did not start.
        RuntimeError
            If the pool has shut down.
        """
        return self._submit(owner, never_released, fn, args, kwargs)

    def _submit(
        self,
        owner: str,
        released: Callable[[], bool],
        fn: Callable[..., R],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Future[R]:
        """Run `fn(*args, **kwargs)` as `submit_as` does, binding *released* to the future."""
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
        return self.submit_as(POOL_OWNER, fn, *args, **kwargs)

    def usage(self) -> Usage:
        """Return the calls counted so far."""
        return self._counts.usage(self.pool_size)

    def shutdown(self, wait: bool = True, *, cancel_futures: bool = False) -> None:
        """Cancel the calls waiting for `start`, then stop the workers."""
        with self._lock:
            if self._state is not State.BROKEN:
                self._state = State.SHUT_DOWN
            waiting = list(self._waiting)
            self._waiting.clear()
        for call in waiting:
            call.future.cancel()
        self._stop(wait, cancel_futures)

    def __enter__(self) -> Self:
        """Start the pool."""
        self.start()
        return self
