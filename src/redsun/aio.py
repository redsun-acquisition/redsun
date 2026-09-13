"""Shared background event loop, and dispatch of coroutines connected to signals.

``redsun`` runs one background `asyncio` event loop per process. Device I/O and
coroutines connected to ``psygnal`` signals run there, off the emitting GUI
thread.

`run_coro` is for general use: synchronous code, such as a presenter method or
a Qt slot, runs a coroutine on the loop with it and gets the result. The rest
of the module is set up by the container at startup and torn down at shutdown.
Components must not build their own loop or install a backend.
"""

from __future__ import annotations

import asyncio
from functools import cache
from threading import Thread
from typing import TYPE_CHECKING, TypeVar, overload

import aiologic as aiol
import psygnal._async
from bluesky.run_engine import _ensure_event_loop_running
from culsans import Queue, QueueShutDown
from psygnal import get_async_backend
from psygnal._async import AsyncioBackend, _AsyncBackend

from redsun.log import Loggable

if TYPE_CHECKING:
    from collections.abc import Coroutine
    from concurrent.futures import Future
    from typing import Any, Literal

    from psygnal._async import QueueItem


class AwaitableEvent:
    """Resettable event whose ``wait`` is a coroutine.

    Wraps `aiologic.REvent`, so the event can be set and cleared from any thread
    and awaited from a coroutine.
    """

    def __init__(self) -> None:
        self._event = aiol.REvent()

    def is_set(self) -> bool:
        """Return ``True`` if the event is set."""
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


R = TypeVar("R")


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
    """``psygnal`` async backend draining a ``culsans`` queue on the shared loop.

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
        """Shut the queue down; the drain cancels pending callbacks."""
        self._queue.shutdown()

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
    """Install the ``culsans`` backend as ``psygnal``'s async backend.

    Call it before connecting a coroutine to a signal. A second call returns the
    installed backend; tear it down with ``psygnal``'s ``clear_async_backend``.

    Returns
    -------
    CulsansAsyncioBackend
        The active backend.

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
    coro: Coroutine[Any, Any, R], return_future: Literal[False] = ...
) -> R: ...
@overload
def run_coro(
    coro: Coroutine[Any, Any, R], return_future: Literal[True] = ...
) -> Future[R]: ...
def run_coro(
    coro: Coroutine[Any, Any, R], return_future: bool = False
) -> R | Future[R]:
    """Run a coroutine in the background event loop and return its result.

    Parameters
    ----------
    coro : collections.abc.Coroutine
        The coroutine to run.
    return_future : bool, optional
        Return the `Future` instead of waiting for the result.

    Returns
    -------
    R
        The result of the coroutine.
    """
    future = asyncio.run_coroutine_threadsafe(coro, get_shared_loop())
    return future if return_future else future.result()


__all__ = [
    "AwaitableEvent",
    "CulsansAsyncioBackend",
    "get_shared_loop",
    "run_coro",
    "set_async_backend",
]
