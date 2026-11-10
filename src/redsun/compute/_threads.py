"""A pool of threads."""

from __future__ import annotations

from concurrent.futures import BrokenExecutor, ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Any, final

from ._future import BrokenPool
from ._pool import Pool

if TYPE_CHECKING:
    from collections.abc import Callable
    from concurrent.futures import Future

    from ._pool import Call


@dataclass(frozen=True, slots=True)
class ThreadPoolSettings:
    """How many threads a thread pool has."""

    threads: int
    """Worker threads; 0 runs each call in the thread that submits it."""

    native_threads: int
    """Threads each worker's native libraries may use."""


def settle_with(call: Call[Any], internal: Future[None]) -> None:
    """Settle *call* when its worker never took it: cancelled, or the workers broke."""
    if internal.cancelled():
        call.future.cancel()
    elif (error := internal.exception()) is not None and not call.future.done():
        call.fail(BrokenPool(f"the workers stopped: {error}"))


@final
class ThreadPool(Pool):
    """Threads several executors share; with `threads=0` a call runs where it is submitted."""

    def __init__(
        self,
        threads: int = 1,
        *,
        native_threads: int = 1,
        initializer: Callable[[], object] | None = None,
    ) -> None:
        super().__init__(native_threads=native_threads)
        self._threads = threads
        self._initializer = initializer
        self._executor: ThreadPoolExecutor | None = None

    @property
    def pool_size(self) -> int:
        """Worker threads."""
        return self._threads

    def _start(self) -> None:
        if self._initializer is not None:
            self._initializer()
        if self._threads:
            self._executor = ThreadPoolExecutor(
                self._threads,
                thread_name_prefix="redsun-compute",
                initializer=self._initializer,
            )

    def _dispatch(self, call: Call[Any]) -> None:
        if self._executor is None:
            call.run()
        else:
            try:
                internal = self._executor.submit(call.run)
            except BrokenExecutor as error:
                raise BrokenPool(f"the workers stopped: {error}") from error
            internal.add_done_callback(partial(settle_with, call))

    def _stop(self, wait: bool, cancel_futures: bool) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait, cancel_futures=cancel_futures)
