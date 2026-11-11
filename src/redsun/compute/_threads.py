"""A pool of threads, and the executor that submits to it."""

from __future__ import annotations

import logging
from concurrent.futures import BrokenExecutor, ThreadPoolExecutor
from functools import partial
from typing import TYPE_CHECKING, Any, final

from ._future import BrokenPool
from ._pool import Pool, PoolExecutor

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from concurrent.futures import Future

    from ._future import Delivery
    from ._pool import Call
    from ._settings import Limits, ThreadPoolSettings

logger = logging.getLogger("redsun")


def settle_with(call: Call[Any], internal: Future[None]) -> None:
    """Settle *call* when its worker never took it: cancelled, or the workers broke."""
    if internal.cancelled():
        call.cancel()
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

    @classmethod
    def resource(
        cls,
        settings: ThreadPoolSettings,
        limits: Limits,
        delivery: Delivery | None = None,
    ) -> Generator[ThreadPool, None, None]:
        """Build a pool from *settings*, yield it unstarted, and stop it at teardown.

        Teardown logs one line on the calls made and does not wait for the
        calls still running.
        """
        pool = cls(
            settings.threads,
            native_threads=settings.native_threads,
            initializer=limits.initializer(settings.native_threads),
        )
        pool._delivery = delivery
        try:
            yield pool
        finally:
            try:
                logger.info(pool._counts.summary("thread pool", pool.pool_size))
            finally:
                pool.shutdown(wait=False, cancel_futures=True)

    @property
    def pool_size(self) -> int:
        """Worker threads."""
        return self._threads

    def _start(self) -> None:
        if self._threads:
            self._executor = ThreadPoolExecutor(
                self._threads,
                thread_name_prefix="redsun-compute",
                initializer=self._initializer,
            )
        elif self._initializer is not None:
            self._initializer()

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


@final
class ThreadExecutor(PoolExecutor[ThreadPool]):
    """Runs one owner's calls on a shared pool of threads."""
