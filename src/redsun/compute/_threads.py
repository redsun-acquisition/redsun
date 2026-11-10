"""A pool of threads."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Any, final

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


def cancel_with(call: Call[Any], internal: Future[None]) -> None:
    """Cancel *call* when its worker never took it."""
    if internal.cancelled():
        call.future.cancel()


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
            self._executor.submit(call.run).add_done_callback(
                partial(cancel_with, call)
            )

    def _stop(self, wait: bool, cancel_futures: bool) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait, cancel_futures=cancel_futures)
