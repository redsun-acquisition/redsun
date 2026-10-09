"""Shared background event loop, and dispatch of coroutines connected to signals.

`redsun` runs one background `asyncio` event loop per process. Device I/O and
coroutines connected to `psygnal` signals run there, off the emitting GUI
thread.

`run_coro` and `cancel_task` are for general use. Synchronous code, such as a
presenter method or a Qt slot, runs a coroutine on the loop with `run_coro` and
gets the result; `cancel_task` stops a task from whichever thread holds it. The rest
of the module is set up by the container at startup and torn down at shutdown.
Components must not build their own loop or install a backend.
"""

from __future__ import annotations

import asyncio
import inspect
from concurrent.futures import wait
from functools import cache
from threading import Thread
from typing import TYPE_CHECKING, Final, TypeVar, overload

import aiologic as aiol
import psygnal._async
from bluesky.run_engine import _ensure_event_loop_running
from culsans import Queue, QueueShutDown
from psygnal import get_async_backend
from psygnal._async import AsyncioBackend, _AsyncBackend

from redsun.log import Loggable

if TYPE_CHECKING:
    from collections.abc import Awaitable
    from concurrent.futures import Future
    from typing import Literal

    from psygnal._async import QueueItem

__all__ = ["cancel_task", "run_coro"]

R = TypeVar("R")

CLOSE_TIMEOUT: Final = 5.0
"""Seconds `CulsansAsyncioBackend.close` waits for the drain to stop."""


class AwaitableEvent:
    """Resettable event whose `wait` is a coroutine.

    Wraps `aiologic.REvent`, so the event can be set and cleared from any thread
    and awaited from a coroutine.
    """

    def __init__(self) -> None:
        self._event = aiol.REvent()

    def is_set(self) -> bool:
        """Return `True` if the event is set."""
        return self._event.is_set()

    def set(self) -> None:
        """Set the event, waking every waiter."""
        self._event.set()

    def clear(self) -> None:
        """Unset the event."""
        self._event.clear()

    async def wait(self) -> None:
        """Wait until the event is set."""
        await self._event


@cache
def get_shared_loop() -> asyncio.AbstractEventLoop:
    """Return the background event loop, starting it on its own thread on first use."""
    loop = asyncio.new_event_loop()
    thread = Thread(target=loop.run_forever, daemon=True)
    thread.start()
    # bluesky's RunEngine looks up the thread of a loop that is already running,
    # and a loop it did not start itself is missing from that registry
    _ensure_event_loop_running.loop_to_thread[loop] = thread  # type: ignore[attr-defined]
    return loop


class CulsansAsyncioBackend(_AsyncBackend, Loggable):
    """`psygnal` async backend draining a `culsans` queue on the shared loop.

    Queued callbacks run as tasks on the loop from `get_shared_loop`, so signals
    emitted on any thread are delivered.
    """

    def __init__(self) -> None:
        super().__init__("culsans")
        self._queue: Queue[QueueItem] = Queue()
        self._running = AwaitableEvent()
        self._draining = False
        self._tasks: set[asyncio.Task[None]] = set()

        # the queue holds callbacks from here on, so work queued before the
        # loop thread picks the drain up is still delivered; marking the
        # backend running only once the drain executes would expose a window
        # in which callers see it as inert when it is not
        self._running.set()
        self._run_task = asyncio.run_coroutine_threadsafe(self.run(), get_shared_loop())

    @property
    def running(self) -> AwaitableEvent:
        """Return the event set while the backend accepts callbacks."""
        return self._running

    def put(self, item: QueueItem) -> None:
        """Queue a callback for dispatch on the shared loop."""
        self._queue.put_nowait(item)

    def close(self) -> None:
        """Shut the queue down, and wait for the drain to stop and cancel pending callbacks.

        Off the shared loop's thread, it returns once the drain has stopped,
        or after `CLOSE_TIMEOUT` seconds; on that thread, at once, since the
        drain can only stop once the call returns.
        """
        self._queue.shutdown()
        if not on_shared_loop():
            wait([self._run_task], timeout=CLOSE_TIMEOUT)

    async def run(self) -> None:
        """Drain the queue until it is shut down or the drain is cancelled."""
        if self._draining:
            return
        self._draining = True
        try:
            loop = get_shared_loop()
            while True:
                item = await self._queue.async_get()
                task = loop.create_task(self.call_back(item))
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)
                task.add_done_callback(self._log_slot_exception)
        except asyncio.CancelledError:
            self.logger.debug("Dispatch cancelled")
        except QueueShutDown:
            self.logger.debug("Dispatch queue shut down")
        except Exception as e:
            self.logger.error(f"Dispatch stopped: {e}", exc_info=e)
        finally:
            self._draining = False
            self._running.clear()
            for task in self._tasks:
                task.cancel()

    def _log_slot_exception(self, task: asyncio.Task[None]) -> None:
        """Report an exception raised by a slot, which nothing else awaits."""
        if task.cancelled():
            return
        if (exc := task.exception()) is not None:
            self.logger.error(f"Exception in async slot: {exc}", exc_info=exc)

    @property
    def name(self) -> str:
        """Name of the backend, for logging and debugging."""
        return f"psygnal-{self._backend}"


# psygnal discriminates on `isinstance(..., AsyncioBackend)` when tearing a
# backend down; without this registration `clear_async_backend()` would drop
# this backend without ever calling `close()`.
AsyncioBackend.register(CulsansAsyncioBackend)


def set_async_backend() -> CulsansAsyncioBackend:
    """Install the `culsans` backend as `psygnal`'s async backend, and return it.

    Call it before connecting a coroutine to a signal. A second call returns the
    installed backend; tear it down with `psygnal`'s `clear_async_backend`.

    Raises
    ------
    RuntimeError
        If a different async backend is already active.
    """
    current = get_async_backend()
    if isinstance(current, CulsansAsyncioBackend):
        return current
    if current is not None:
        raise RuntimeError(f"Async backend already set to: {current._backend}")

    backend = CulsansAsyncioBackend()

    # psygnal resolves the active backend through its own module global, so
    # binding a name here is not enough for `get_async_backend()` to find it
    psygnal._async._ASYNC_BACKEND = backend
    return backend


@overload
def run_coro(
    awaitable: Awaitable[R],
    return_future: Literal[False] = False,
    *,
    timeout: float | None = None,
) -> R: ...
@overload
def run_coro(awaitable: Awaitable[R], return_future: Literal[True]) -> Future[R]: ...
def run_coro(
    awaitable: Awaitable[R],
    return_future: bool = False,
    *,
    timeout: float | None = None,
) -> R | Future[R]:
    """Run *awaitable* on the shared loop and return its result.

    With *return_future*, return the `Future` at once instead of waiting; that
    is safe from any thread, the shared loop's own included. A wait that ends
    without a result, on *timeout* or when the waiting thread is interrupted,
    cancels *awaitable*.

    Parameters
    ----------
    timeout
        Seconds to wait; `None` waits until it completes.

    Raises
    ------
    RuntimeError
        If called on the shared loop's thread without *return_future*, where
        waiting would block the loop that has to run *awaitable*.
    TimeoutError
        If *timeout* passes first.
    """
    loop = get_shared_loop()
    if not return_future and on_shared_loop():
        if inspect.iscoroutine(awaitable):
            # never scheduled: closing it avoids "coroutine was never awaited"
            awaitable.close()
        raise RuntimeError(
            "run_coro was called on the shared loop's thread, where waiting "
            "would block it; await the coroutine, or pass return_future=True"
        )
    future = asyncio.run_coroutine_threadsafe(coroutine_of(awaitable), loop)
    if return_future:
        return future
    try:
        return future.result(timeout)
    except BaseException:
        # a timeout or an interrupt: nobody waits for the result any more
        future.cancel()
        raise


def cancel_task(task: asyncio.Future[R]) -> None:
    """Cancel *task* from any thread.

    The cancellation is handed to the task's loop and reaches the task the
    next time it waits, or not at all if it has finished by then.
    """
    # a task cancelled from another thread while it runs is cancelled again
    # once it returns, after it finished its work
    task.get_loop().call_soon_threadsafe(task.cancel)


def on_shared_loop() -> bool:
    """Return whether the calling thread is the one running the shared loop."""
    try:
        return asyncio.get_running_loop() is get_shared_loop()
    except RuntimeError:
        return False


async def coroutine_of(awaitable: Awaitable[R]) -> R:
    """Return what *awaitable* gives, as a coroutine the loop can schedule."""
    return await awaitable
