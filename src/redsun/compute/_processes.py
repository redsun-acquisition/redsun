"""A pool of worker processes, and the executor that submits to it."""

from __future__ import annotations

import logging
import multiprocessing
import threading
import time
from collections import deque
from concurrent.futures import BrokenExecutor, ProcessPoolExecutor
from concurrent.futures import wait as wait_for
from functools import partial
from logging.handlers import QueueListener
from queue import Empty
from typing import TYPE_CHECKING, Any, Final, final

from ._future import BrokenPool, WorkerCrashed, trace
from ._pickling import check_function, round_trip
from ._pool import Pool, PoolExecutor
from ._worker import prepare_worker

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from concurrent.futures import Future
    from multiprocessing.queues import Queue

    from ._future import Delivery
    from ._pool import Call
    from ._settings import Limits, Priority, ProcessPoolSettings

POLL_INTERVAL: Final = 0.1
MAX_REPLACEMENTS: Final = 3
REPLACEMENT_WINDOW: Final = 60.0
LISTENER_TIMEOUT: Final = 1.0

logger = logging.getLogger("redsun")


class FileUnder(logging.Handler):
    """File each record it gets under the logger *name*, whatever it was named."""

    def __init__(self, name: str) -> None:
        super().__init__()
        self._name = name

    def emit(self, record: logging.LogRecord) -> None:
        """Hand *record* to the logger named after the pool."""
        record.name = self._name
        logging.getLogger(self._name).handle(record)


class PollingListener(QueueListener):
    """Hand the records of a worker log queue to handlers, and stop without writing to the queue.

    `stop` sets a flag the listener thread checks between reads, so it returns
    even when a terminated worker left the queue's write lock held. Records
    already in the queue are handed over before the thread ends.
    """

    def __init__(self, source: Queue[Any], *handlers: logging.Handler) -> None:
        super().__init__(source, *handlers)
        self._source = source
        self._finished = threading.Event()

    def dequeue(self, block: bool) -> Any:
        """Return the next record, or `None`, the end marker, once stopped and the queue is empty."""
        while True:
            try:
                return self._source.get(timeout=POLL_INTERVAL)
            except Empty:
                if self._finished.is_set():
                    return None

    def enqueue_sentinel(self) -> None:
        """Ask the listener thread to end once the queue is empty."""
        self._finished.set()

    def stop(self, timeout: float | None = None) -> None:
        """Ask the listener thread to end, and wait for it at most *timeout* seconds.

        A thread still running after *timeout* is logged as a warning and left
        behind: a worker ended while writing a record can leave a partial one
        the thread waits on for ever.
        """
        thread = self._thread
        if thread is None:
            return
        self.enqueue_sentinel()
        thread.join(timeout)
        if thread.is_alive():
            logger.warning(
                f"The log listener of a process pool did not stop in {timeout:g} s;"
                " a worker may have ended while writing a record"
            )
        self._thread = None


@final
class ProcessPool(Pool):
    """Worker processes several executors share; with `workers=0` a call runs where it is submitted.

    A call runs in a worker only if its function and arguments survive
    pickling. A function defined at module level of an importable module is
    sent by name; a lambda, a closure, a bound method or a function defined in
    the script being run is refused at `submit`. With `workers=0` each call
    and its result still make a pickle round trip.

    Workers start with the `spawn` method, so a script that starts a pool must
    be guarded by `if __name__ == "__main__":`. The workers' log records reach
    the session's log under *log_name*. Shutting the pool down waits for
    running calls at most *stop_timeout* seconds, then ends the workers
    still running, which fails their calls with `BrokenPool`.

    A worker that ends while calls are unfinished fails every one of them
    with `WorkerCrashed` once the pool has started new workers. Replaced more
    than 3 times within 60 s, the pool breaks instead and refuses later calls
    with `BrokenPool`.

    Parameters
    ----------
    workers
        Worker processes; 0 runs each call in the thread that submits it.
    priority
        The priority the workers start at.
    stop_timeout
        Seconds `shutdown` waits for running calls before ending the workers.
    log_name
        Name of the logger the workers' records are filed under.
    """

    def __init__(
        self,
        workers: int = 1,
        *,
        priority: Priority = "normal",
        stop_timeout: float = 10.0,
        log_name: str = "redsun.workers",
    ) -> None:
        super().__init__()
        self._workers = workers
        self._priority = priority
        self._stop_timeout = stop_timeout
        self._log_name = log_name
        self._executor: ProcessPoolExecutor | None = None
        self._listener: PollingListener | None = None
        self._queue: Queue[Any] | None = None
        self._inflight: set[Future[Any]] = set()
        # not the pool lock: done-callbacks take it under the standard pool's own lock
        self._inflight_lock = threading.Lock()
        self._crashed: dict[
            ProcessPoolExecutor, list[tuple[Call[Any], BaseException]]
        ] = {}
        self._replaced: deque[float] = deque()
        self._stopping = False

    @classmethod
    def resource(
        cls,
        settings: ProcessPoolSettings,
        limits: Limits,
        delivery: Delivery | None = None,
        owner: str = "<pool>",
    ) -> Generator[ProcessPool, None, None]:
        """Build a pool from *settings*, yield it unstarted, and stop it at teardown.

        Teardown logs one line on the calls made, then waits for the running
        calls as `shutdown` does.
        """
        pool = cls(
            settings.processes,
            priority=settings.priority,
            log_name=f"redsun.workers.{owner}",
        )
        pool._native_threads = settings.native_threads
        pool._delivery = delivery
        try:
            yield pool
        finally:
            try:
                logger.info(pool._counts.summary("process pool", pool.pool_size))
            finally:
                pool.shutdown(wait=True)

    @property
    def pool_size(self) -> int:
        """Worker processes."""
        return self._workers

    def _check(self, fn: Callable[..., Any]) -> None:
        check_function(fn)

    def _start(self) -> None:
        if not self._workers:
            return
        queue = multiprocessing.get_context("spawn").Queue()
        listener = PollingListener(queue, FileUnder(self._log_name))
        listener.start()
        try:
            self._executor = self._new_executor(queue)
        except Exception:
            listener.stop()
            raise
        self._listener = listener
        self._queue = queue

    def _new_executor(self, queue: Queue[Any]) -> ProcessPoolExecutor:
        """Return a standard pool whose workers log to the pool's queue."""
        return ProcessPoolExecutor(
            self._workers,
            mp_context=multiprocessing.get_context("spawn"),
            initializer=prepare_worker,
            initargs=(
                queue,
                logger.getEffectiveLevel(),
                self._priority,
                self._native_threads,
            ),
        )

    def _replace(
        self, broken: ProcessPoolExecutor, error: BaseException
    ) -> ProcessPoolExecutor | None:
        """Replace *broken* with a new standard pool, or break the pool after too many replacements.

        Only the first caller naming a given *broken* replaces it; the others
        get the pool's current one. `None` means the pool broke or shut down.
        """
        with self._lock:
            if self._executor is not broken or self._queue is None:
                return self._executor
            logging.getLogger(self._log_name).error(
                f"A worker process ended: {trace(error)}"
            )
            now = time.monotonic()
            self._replaced.append(now)
            while now - self._replaced[0] > REPLACEMENT_WINDOW:
                self._replaced.popleft()
            if len(self._replaced) > MAX_REPLACEMENTS:
                self._executor = None
                self._break(
                    f"the pool was replaced more than {MAX_REPLACEMENTS} times"
                    f" in {REPLACEMENT_WINDOW:g} s"
                )
                return None
            self._executor = self._new_executor(self._queue)
            return self._executor

    def _send(
        self, executor: ProcessPoolExecutor, call: Call[Any]
    ) -> tuple[ProcessPoolExecutor, Future[Any]]:
        """Submit *call* to *executor*, or once to its replacement if it broke.

        Returns the executor that took the call and its future.

        Raises
        ------
        BrokenPool
            If the pool broke or shut down, or the replacement broke too.
        """
        try:
            return executor, executor.submit(call.fn, *call.args, **call.kwargs)
        except BrokenExecutor as error:
            replacement = self._replace(executor, error)
            if replacement is None:
                raise BrokenPool(self._broken or "the pool shut down") from error
        try:
            return replacement, replacement.submit(call.fn, *call.args, **call.kwargs)
        except BrokenExecutor as error:
            raise BrokenPool(f"the workers stopped: {error}") from error

    def _dispatch(self, call: Call[Any]) -> None:
        if not self._workers:
            call.run(through=round_trip)
            return
        future = call.future
        waited = time.monotonic() - call.submitted
        # a worker may take the call before submit returns, so cancels wait for the link
        if not future._hand_over():
            call.cancel()
            return
        executor = self._executor
        try:
            if executor is None:
                raise BrokenPool(self._broken or "the pool shut down")
            executor, standard = self._send(executor, call)
        except BaseException:
            future._link(None)
            raise
        future._link(standard, partial(self._counts.started, call.owner, waited))
        with self._inflight_lock:
            self._inflight.add(standard)
        standard.add_done_callback(partial(self._settle, call, executor))

    def _settle(
        self, call: Call[Any], executor: ProcessPoolExecutor, standard: Future[Any]
    ) -> None:
        """Settle *call* from the worker's answer, or from its being cancelled or ended.

        Runs on the standard pool's thread, under its lock when a worker
        ended, so a crashed call is left to `_recover` on a thread of its own:
        callbacks that submit again must not run under that lock.
        """
        with self._inflight_lock:
            self._inflight.discard(standard)
        future = call.future
        if standard.cancelled():
            future._linked = None
            self._counts.unstarted(call.owner)
            call.cancel()
            return
        if not future.set_running_or_notify_cancel():
            self._counts.unstarted(call.owner)
            return
        future._linked = None
        error = standard.exception()
        if isinstance(error, BrokenExecutor):
            if not self._stopping:
                with self._inflight_lock:
                    crashed = self._crashed.setdefault(executor, [])
                    crashed.append((call, error))
                    first = len(crashed) == 1
                if first:
                    threading.Thread(
                        target=self._recover,
                        args=(executor,),
                        name="redsun-process-pool-recover",
                        daemon=True,
                    ).start()
                return
            error = BrokenPool("the pool shut down")
        self._counts.finished(call.owner, failed=error is not None)
        if error is None:
            future.set_result(standard.result())
        else:
            future.set_exception(error)

    def _recover(self, broken: ProcessPoolExecutor) -> None:
        """Replace *broken*, then fail the calls it left unfinished with `WorkerCrashed`."""
        while True:
            with self._inflight_lock:
                crashed = self._crashed.pop(broken, [])
            if not crashed:
                return
            try:
                self._replace(broken, crashed[0][1])
            finally:
                for call, error in crashed:
                    self._counts.crashed(call.owner)
                    self._counts.finished(call.owner, failed=True)
                    failure = WorkerCrashed(
                        f"a worker process of {call.owner}"
                        " ended before the call finished"
                    )
                    failure.__cause__ = error
                    call.future.set_exception(failure)

    def _stop(self, wait: bool, cancel_futures: bool) -> None:
        """Wait for the running calls, end the workers still running, and stop the log listener.

        Always waits up to `stop_timeout`, and always cancels the calls no
        worker has taken.
        """
        with self._lock:
            self._stopping = True
            executor, self._executor = self._executor, None
            listener, self._listener = self._listener, None
            queue, self._queue = self._queue, None
        with self._inflight_lock:
            inflight = list(self._inflight)
        terminated = False
        if executor is not None:
            # shortcut: private _processes until 3.14 is the oldest Python; then terminate_workers()
            # read before shutdown, which empties it on 3.14 too
            processes = list(executor._processes.values())
            executor.shutdown(wait=False, cancel_futures=True)
            _, unfinished = wait_for(inflight, timeout=self._stop_timeout)
            if unfinished:
                for process in processes:
                    process.terminate()
                for process in processes:
                    process.join(self._stop_timeout)
                terminated = True
            else:
                executor.shutdown(wait=True)
        with self._lock:
            replaced = bool(self._replaced)
        with self._inflight_lock:
            crashed = bool(self._crashed)
        # shortcut: private _broken, the stdlib's only sign of a worker that died with no call running; drop it if that case stops mattering
        broken = executor is not None and bool(executor._broken)
        # a worker that ended, by crash or terminate, may have left a partial record
        ended = terminated or replaced or crashed or broken
        if listener is not None:
            listener.stop(LISTENER_TIMEOUT if ended else None)
        if queue is not None:
            queue.close()


@final
class ProcessExecutor(PoolExecutor[ProcessPool]):
    """Runs one owner's calls on a shared pool of worker processes."""
