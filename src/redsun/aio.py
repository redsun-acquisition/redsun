from __future__ import annotations

import asyncio
from threading import Thread
from typing import TYPE_CHECKING, ClassVar, TypeVar, overload

from bluesky.run_engine import _ensure_event_loop_running

if TYPE_CHECKING:
    from collections.abc import Coroutine
    from concurrent.futures import Future
    from typing import Any, Literal

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


_loop_factory = _LoopFactory()
#: Global factory for shared background event loop. Not public.


def get_shared_loop() -> asyncio.AbstractEventLoop:
    """Return the background event loop.

    Returns
    -------
    asyncio.AbstractEventLoop
        The shared event loop.
    """
    return _loop_factory()


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
    return future if return_future else future.result()


__all__ = [
    "get_shared_loop",
    "run_coro",
]
