"""A pool of worker processes, and the executor that submits to it."""

from __future__ import annotations

import logging
import multiprocessing
import threading
import time
from concurrent.futures import BrokenExecutor, ProcessPoolExecutor
from concurrent.futures import wait as wait_for
from functools import partial
from logging.handlers import QueueListener
from queue import Empty
from typing import TYPE_CHECKING, Any, Final, final

from ._future import BrokenPool
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
        self._listener: QueueListener | None = None
        self._queue: Queue[Any] | None = None
        self._inflight: set[Future[Any]] = set()
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
        context = multiprocessing.get_context("spawn")
        queue = context.Queue()
        listener = PollingListener(queue, FileUnder(self._log_name))
        listener.start()
        try:
            self._executor = ProcessPoolExecutor(
                self._workers,
                mp_context=context,
                initializer=prepare_worker,
                initargs=(
                    queue,
                    logger.getEffectiveLevel(),
                    self._priority,
                    self._native_threads,
                ),
            )
        except Exception:
            listener.stop()
            raise
        self._listener = listener
        self._queue = queue

    def _dispatch(self, call: Call[Any]) -> None:
        if not self._workers:
            call.run(through=round_trip)
            return
        if self._executor is None:
            raise BrokenPool("the pool shut down")
        future = call.future
        if future.cancelled():
            call.cancel()
            return
        waited = time.monotonic() - call.submitted
        try:
            standard = self._executor.submit(call.fn, *call.args, **call.kwargs)
        except BrokenExecutor as error:
            raise BrokenPool(f"the workers stopped: {error}") from error
        self._counts.started(call.owner, waited)
        future._linked = standard
        with self._lock:
            self._inflight.add(standard)
        standard.add_done_callback(partial(self._settle, call))

    def _settle(self, call: Call[Any], standard: Future[Any]) -> None:
        """Settle *call* from the worker's answer, or from its being cancelled or ended."""
        with self._lock:
            self._inflight.discard(standard)
        future = call.future
        future._linked = None
        if standard.cancelled() or future.cancelled():
            self._counts.unstarted(call.owner)
            call.cancel()
            return
        error = standard.exception()
        if isinstance(error, BrokenExecutor):
            error = BrokenPool(
                "the pool shut down"
                if self._stopping
                else f"the workers stopped: {error}"
            )
        future.set_running_or_notify_cancel()
        self._counts.finished(call.owner, failed=error is not None)
        if error is None:
            future.set_result(standard.result())
        else:
            future.set_exception(error)

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
            inflight = list(self._inflight)
        if executor is None:
            return
        # shortcut: private _processes, read before shutdown empties it; no public way to list the workers
        processes = list(executor._processes.values())
        executor.shutdown(wait=False, cancel_futures=True)
        _, unfinished = wait_for(inflight, timeout=self._stop_timeout)
        if unfinished:
            for process in processes:
                process.terminate()
            for process in processes:
                process.join(self._stop_timeout)
        else:
            executor.shutdown(wait=True)
        if listener is not None:
            listener.stop()
        if queue is not None:
            queue.close()


@final
class ProcessExecutor(PoolExecutor[ProcessPool]):
    """Runs one owner's calls on a shared pool of worker processes."""
