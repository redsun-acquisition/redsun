"""Shared background event loop and dispatch of coroutines connected to signals.

Redsun runs one background `asyncio` event loop for the whole process. Device
I/O and any coroutine connected to a psygnal signal execute there, off the GUI
thread that emits.

Only `run_coro` is meant for general use: it is how synchronous code — a
presenter method, a Qt slot — runs a coroutine on that loop and gets its
result. Everything else in this module is application plumbing, set up by the
application container during startup and torn down on shutdown. Components
should not build a loop or install a backend of their own.
"""

from __future__ import annotations

import asyncio
from threading import Thread
from typing import TYPE_CHECKING, ClassVar, TypeVar, overload

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

    Wraps `aiologic.REvent` so that the event can be set and cleared from any
    thread while still being awaited from a coroutine.
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


class _LoopFactory:
    """Factory for a shared background event loop.

    Not public API.
    """

    _loop: ClassVar[asyncio.AbstractEventLoop | None] = None
    _thread: ClassVar[Thread | None] = None

    def __call__(self) -> asyncio.AbstractEventLoop:
        if _LoopFactory._loop is None:
            loop = asyncio.new_event_loop()
            thread = Thread(target=loop.run_forever, daemon=True)
            thread.start()

            # this is a hack to make sure that the internal function
            # that caches the event loop associated with the current thread
            # is already aware of the loop we just created
            _ensure_event_loop_running.loop_to_thread[loop] = thread  # type: ignore

            _LoopFactory._loop = loop
            _LoopFactory._thread = thread
        return _LoopFactory._loop

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        return self()


#: Global factory for shared background event loop. Not public.
_loop_factory = _LoopFactory()


def get_shared_loop() -> asyncio.AbstractEventLoop:
    """Return the background event loop.

    Returns
    -------
    asyncio.AbstractEventLoop
        The shared event loop.
    """
    return _loop_factory()


class CulsansAsyncioBackend(_AsyncBackend, Loggable):
    """Psygnal async backend draining a culsans queue on the shared loop.

    Queued callbacks are dispatched as tasks on the loop returned by
    `get_shared_loop`, so signals emitted from any thread are delivered.
    """

    def __init__(self) -> None:
        super().__init__("culsans")
        self._queue: Queue[QueueItem] = Queue()
        self._running = AwaitableEvent()
        self._tasks: set[asyncio.Task[None]] = set()
        self._run_task = asyncio.run_coroutine_threadsafe(self.run(), get_shared_loop())

    @property
    def running(self) -> AwaitableEvent:
        """Return the event indicating if the backend is running."""
        return self._running

    def put(self, item: QueueItem) -> None:
        """Queue a callback for dispatch on the shared loop."""
        self._queue.put_nowait(item)

    def close(self) -> None:
        """Shut the queue down; the drain cancels outstanding callbacks."""
        self._queue.shutdown()

    async def run(self) -> None:
        """Drain the queue until it is shut down or the drain is cancelled."""
        if self._running.is_set():
            return
        self._running.set()
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
        """Name of the backend, for logging and debugging purposes."""
        return f"psygnal-{self._backend}"


# psygnal discriminates on `isinstance(..., AsyncioBackend)` when tearing a
# backend down; without this registration `clear_async_backend()` would drop
# this backend without ever calling `close()`.
AsyncioBackend.register(CulsansAsyncioBackend)


def set_async_backend() -> CulsansAsyncioBackend:
    """Install the culsans backend as psygnal's active async backend.

    Must be called before connecting a coroutine to a signal. Calling it
    again returns the backend installed by the first call; tear it down with
    psygnal's own ``clear_async_backend``.

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
        If ``True``, return the `Future` object instead of waiting for the result.

    Returns
    -------
    R
        The result of the coroutine.
    """
    future = asyncio.run_coroutine_threadsafe(coro, _loop_factory())
    return future if return_future else future.result()


__all__ = [
    "AwaitableEvent",
    "CulsansAsyncioBackend",
    "get_shared_loop",
    "run_coro",
    "set_async_backend",
]
