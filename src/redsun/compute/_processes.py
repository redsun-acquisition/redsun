"""A pool of worker processes."""

from __future__ import annotations

import concurrent.futures
import itertools
import logging
import os
import queue
import sys
import threading
import time
from collections import deque
from functools import partial
from multiprocessing.connection import Client, Listener
from typing import TYPE_CHECKING, Any, Final, final

from redsun.services import Service
from redsun.workers import ADDRESS_VARIABLE, AUTHKEY_VARIABLE

from ..services._transports import SHAREDBOX
from ._channel import Channel, UnreadableMessage
from ._future import BrokenPool, WorkerCrashed
from ._pickling import check_function, name_of, round_trip
from ._pool import Pool, State
from ._settings import Limits

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Mapping

    from ._future import Delivery
    from ._pool import Call
    from ._settings import Priority, ProcessPoolSettings

WORKER_READY: Final = "redsun worker ready"
"""Line a worker process prints once it has connected to its pool."""

CRASHES_PER_CALL: Final = 3
"""Workers a call may end before it fails with `WorkerCrashed`."""

MAX_RESTARTS: Final = 5
"""Restarts within `RESTART_WINDOW` a pool allows before it breaks."""

RESTART_WINDOW: Final = 60.0
"""Seconds over which restarts are counted."""

TOO_MANY_RESTARTS: Final = (
    f"the workers restarted more than {MAX_RESTARTS} times in {RESTART_WINDOW:g} s"
)

SHUT_DOWN: Final = "the pool shut down"

EXIT_POLL: Final = 0.01
"""Seconds between checks that a worker whose pipe closed has exited."""

numbers = itertools.count(1)
"""Numbers the worker processes of this process are named after."""

logger = logging.getLogger("redsun")


class PipeClosed(EOFError):
    """Raised by `Worker.call` when the pipe to the worker closed."""


class Worker:
    """One started worker process and the channel to it."""

    __slots__ = ("channel", "ids", "service")

    def __init__(self, service: Service, channel: Channel) -> None:
        self.service = service
        self.channel = channel
        self.ids = itertools.count(1)

    def call(
        self, fn: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]
    ) -> Any:
        """Return what `fn(*args, **kwargs)` returns in the worker.

        Raises
        ------
        PipeClosed
            If the pipe closed before the answer arrived.
        TypeError
            If the call cannot be pickled, or its answer cannot be read here.
        Exception
            The error the call raised in the worker.
        """
        id = next(self.ids)
        try:
            self.channel.send("call", id, (fn, args, kwargs))
            kind, _, answer = self.channel.receive()
        except UnreadableMessage as unreadable:
            raise TypeError(
                f"the answer of {name_of(fn)}() cannot be read in this process: "
                f"{unreadable.error}"
            ) from unreadable.error
        except (EOFError, OSError) as error:
            raise PipeClosed(str(error)) from error
        if kind == "error":
            raise answer
        return answer

    def stop(self) -> None:
        """Stop the process, then close the channel and unlink its rings.

        The process goes first, so a thread still waiting on the pipe sees it
        close before the channel does.
        """
        self.service.stop()
        self.channel.close()

    def stop_ended(self) -> None:
        """Stop a worker whose pipe closed once its process exits, or after `stop_timeout`.

        A process that exits before `stop` is logged as an unexpected exit,
        with its exit code and last output.
        """
        # the pipe closes a moment before the process counts as exited
        deadline = time.monotonic() + self.service.stop_timeout
        while self.service.running and time.monotonic() < deadline:
            time.sleep(EXIT_POLL)
        self.stop()


def accept_into(
    listener: Listener, accepted: concurrent.futures.Future[Channel]
) -> None:
    """Settle *accepted* with a channel over the next connection *listener* accepts."""
    try:
        accepted.set_result(Channel(listener.accept()))
    except BaseException as error:  # noqa: BLE001 - the spawning thread raises it
        accepted.set_exception(error)


def spawn_worker(
    listener: Listener,
    authkey: bytes,
    *,
    env: Mapping[str, str],
    priority: Priority,
    stop_timeout: float,
) -> Worker:
    """Start a worker process and accept its connection to *listener*.

    Raises
    ------
    TimeoutError
        If the worker does not become ready in time.
    RuntimeError
        If the worker exits before it is ready.
    """
    service = Service(
        f"worker-{next(numbers)}",
        module="redsun.workers",
        ready=WORKER_READY,
        # the transport that reserves nothing: a worker is reached through
        # its pipe alone
        transport=SHAREDBOX,
        env=env,
        priority=priority,
        stop_timeout=stop_timeout,
    )
    accepted: concurrent.futures.Future[Channel] = concurrent.futures.Future()
    # the worker connects before it prints its readiness line, and on Windows
    # its connection completes only once accept runs
    threading.Thread(
        target=accept_into,
        args=(listener, accepted),
        name=f"redsun-accept-{service.name}",
        daemon=True,
    ).start()
    try:
        service.start()
    except BaseException:
        if not accepted.done():
            # wake the accept the worker never reached
            Client(listener.address, authkey=authkey).close()
        accepted.result(timeout=service.startup_timeout).close()
        raise
    try:
        channel = accepted.result(timeout=service.startup_timeout)
    except BaseException:
        service.stop()
        raise
    return Worker(service, channel)


@final
class ProcessPool(Pool):
    """Processes several executors share; with `processes=0` a call runs where it is submitted."""

    def __init__(
        self,
        processes: int = 1,
        *,
        native_threads: int = 1,
        priority: Priority = "normal",
        stop_timeout: float = 5.0,
    ) -> None:
        super().__init__(native_threads=native_threads)
        self._processes = processes
        self._priority = priority
        self._stop_timeout = stop_timeout
        self._queue: queue.SimpleQueue[Call[Any] | None] = queue.SimpleQueue()
        self._threads: list[threading.Thread] = []
        self._workers: list[Worker | None] = []
        self._listener: Listener | None = None
        self._authkey = b""
        self._env: dict[str, str] = {}
        # one spawn at a time, so each accept takes the connection of the
        # worker it waits for
        self._spawning = threading.Lock()
        self._restarts: deque[float] = deque()
        self._stopping = False

    @classmethod
    def resource(
        cls,
        settings: ProcessPoolSettings,
        limits: Limits,
        delivery: Delivery | None = None,
    ) -> Generator[ProcessPool, None, None]:
        """Build a pool from *settings*, yield it unstarted, and stop it at teardown.

        Teardown logs one line on the calls made and does not wait for the
        calls still running.
        """
        pool = cls(
            settings.processes,
            native_threads=settings.native_threads,
            priority=settings.priority,
        )
        pool._delivery = delivery
        try:
            yield pool
        finally:
            try:
                logger.info(pool._counts.summary("process pool", pool.pool_size))
            finally:
                pool.shutdown(wait=False, cancel_futures=True)

    @property
    def pool_size(self) -> int:
        """Worker processes."""
        return self._processes

    def _check(self, fn: Callable[..., Any]) -> None:
        check_function(fn)

    def _start(self) -> None:
        if not self._processes:
            return
        if not getattr(sys, "_is_gil_enabled", lambda: True)():
            targets = [round_trip] * self._processes
        else:
            self._start_workers()
            targets = [partial(self._send, slot) for slot in range(self._processes)]
        self._threads = [
            threading.Thread(
                target=self._serve,
                args=(through,),
                name=f"redsun-worker-{slot + 1}",
                daemon=True,
            )
            for slot, through in enumerate(targets)
        ]
        for thread in self._threads:
            thread.start()

    def _start_workers(self) -> None:
        """Listen for workers and start `processes` of them, stopping them all if one fails."""
        self._authkey = os.urandom(32)
        self._listener = Listener(authkey=self._authkey)
        self._env = {
            ADDRESS_VARIABLE: str(self._listener.address),
            AUTHKEY_VARIABLE: self._authkey.hex(),
            **Limits.environment(self._native_threads),
        }
        try:
            for _ in range(self._processes):
                self._workers.append(self._spawn())
        except BaseException:
            for worker in self._workers:
                if worker is not None:
                    worker.stop()
            self._workers.clear()
            self._listener.close()
            self._listener = None
            raise

    def _spawn(self) -> Worker:
        """Start one worker, at normal priority once the system refused the pool's."""
        assert self._listener is not None
        with self._spawning:
            worker = spawn_worker(
                self._listener,
                self._authkey,
                env=self._env,
                priority=self._priority,
                stop_timeout=self._stop_timeout,
            )
            # the refusal is logged once, by the first worker refused
            if worker.service.priority != self._priority:
                self._priority = worker.service.priority
        return worker

    def _dispatch(self, call: Call[Any]) -> None:
        if not self._processes:
            call.run(through=round_trip)
            return
        with self._lock:
            if self._state is State.BROKEN:
                raise BrokenPool(self._broken)
            if self._stopping:
                raise RuntimeError("cannot schedule new futures after shutdown")
            self._queue.put(call)

    def _serve(
        self,
        through: Callable[[Callable[..., Any], tuple[Any, ...], dict[str, Any]], Any],
    ) -> None:
        """Run the queued calls through *through* until a `None` arrives."""
        while True:
            call = self._queue.get()
            if call is None:
                return
            call.run(through=through)
            # an idle thread would otherwise hold the last call's arguments
            del call

    def _send(
        self,
        slot: int,
        fn: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        """Run a call on the worker of *slot*, replacing the worker each time it ends.

        Raises
        ------
        WorkerCrashed
            If the call ended `CRASHES_PER_CALL` workers.
        BrokenPool
            If the pool broke or shut down, or broke replacing the worker.
        """
        crashes = 0
        while True:
            worker = self._workers[slot]
            if worker is None:
                raise BrokenPool(self._broken or SHUT_DOWN)
            try:
                # one call in flight per worker, and a worker sends nothing but
                # the answer to it: Channel.send reads anything else arriving
                # during a ring send as the worker having gone
                return worker.call(fn, args, kwargs)
            except PipeClosed:
                pass
            self._replace(slot)
            crashes += 1
            if crashes == CRASHES_PER_CALL:
                raise WorkerCrashed(f"the call ended {CRASHES_PER_CALL} workers")

    def _replace(self, slot: int) -> None:
        """Stop the worker of *slot* after it ended, and start another in its place.

        Raises
        ------
        BrokenPool
            If the pool is shutting down or broken, restarted too often, or
            the new worker did not start.
        """
        with self._lock:
            if self._stopping:
                raise BrokenPool(SHUT_DOWN)
            if self._state is State.BROKEN:
                raise BrokenPool(self._broken)
            ended = self._workers[slot]
            self._workers[slot] = None
            now = time.monotonic()
            self._restarts.append(now)
            while self._restarts[0] < now - RESTART_WINDOW:
                self._restarts.popleft()
            too_many = len(self._restarts) > MAX_RESTARTS
        if ended is not None:
            ended.stop_ended()
        if too_many:
            self._break_and_fail(TOO_MANY_RESTARTS)
            raise BrokenPool(TOO_MANY_RESTARTS)
        try:
            worker = self._spawn()
        except Exception as error:
            reason = f"a worker did not start: {error}"
            self._break_and_fail(reason)
            raise BrokenPool(reason) from error
        if not self._register(slot, worker):
            worker.stop()
            raise BrokenPool(SHUT_DOWN)

    def _register(self, slot: int, worker: Worker) -> bool:
        """Make *worker* the worker of *slot*, unless the pool is stopping."""
        with self._lock:
            if self._stopping:
                return False
            self._workers[slot] = worker
            return True

    def _break_and_fail(self, reason: str) -> None:
        """Break the pool and fail every call still queued for a worker."""
        with self._lock:
            self._break(reason)
            queued = self._take_queued()
        for call in queued:
            call.fail(BrokenPool(reason))

    def _take_queued(self) -> list[Call[Any]]:
        """Remove and return the calls no worker took yet, leaving the stop markers."""
        taken: list[Call[Any]] = []
        markers = 0
        while True:
            try:
                call = self._queue.get_nowait()
            except queue.Empty:
                break
            if call is None:
                markers += 1
            else:
                taken.append(call)
        for _ in range(markers):
            self._queue.put(None)
        return taken

    def _stop(self, wait: bool, cancel_futures: bool) -> None:
        with self._lock:
            if self._stopping:
                return
            self._stopping = True
            queued = self._take_queued() if cancel_futures else []
        for call in queued:
            call.cancel()
        for _ in self._threads:
            self._queue.put(None)
        if wait:
            for thread in self._threads:
                thread.join()
        with self._lock:
            workers = [worker for worker in self._workers if worker is not None]
        # ending the processes first ends the calls still running, so the
        # threads return before any channel closes under them
        for worker in workers:
            worker.service.stop()
        for thread in self._threads:
            thread.join()
        for worker in workers:
            worker.stop()
        if self._listener is not None:
            self._listener.close()
