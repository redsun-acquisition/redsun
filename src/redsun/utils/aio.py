from __future__ import annotations

import asyncio
from threading import Thread
from typing import TYPE_CHECKING, TypeVar, overload

from bluesky.run_engine import _ensure_event_loop_running

if TYPE_CHECKING:
    from collections.abc import Coroutine
    from concurrent.futures import Future
    from typing import Any, Literal

_shared_loop: asyncio.AbstractEventLoop | None = None
_loop_thread: Thread | None = None

R = TypeVar("R")


# TODO: this should be made into a factory
# class to prevent the usage of global variables...
def get_shared_loop() -> asyncio.AbstractEventLoop:
    """Return the background event loop.

    Returns
    -------
    asyncio.AbstractEventLoop
        The shared event loop.
    """
    global _shared_loop
    global _loop_thread
    if _shared_loop is None:
        # at first call of this function,
        # creates a new event loop and starts it in a background thread;
        # subsequent calls will return the same event loop.
        # this will be the same event loop of all
        # RunEngine instances that use the default value of the loop parameter.
        _shared_loop = asyncio.new_event_loop()
        _loop_thread = Thread(target=_shared_loop.run_forever, daemon=True)
        _loop_thread.start()

        # this is a hack to make sure that the internal function
        # that caches the event loop associated with the current thread
        # is already aware of the loop we just created
        _ensure_event_loop_running.loop_to_thread[_shared_loop] = _loop_thread  # type: ignore
    return _shared_loop


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
    future = asyncio.run_coroutine_threadsafe(coro, get_shared_loop())
    if return_future:
        return future
    else:
        return future.result()


__all__ = [
    "get_shared_loop",
    "run_coro",
]
