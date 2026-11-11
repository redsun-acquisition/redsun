"""A pool of worker processes."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, final

from ._pickling import check_function, round_trip
from ._pool import Pool

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from ._future import Delivery
    from ._pool import Call
    from ._settings import Limits, Priority, ProcessPoolSettings

logger = logging.getLogger("redsun")


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

    def _dispatch(self, call: Call[Any]) -> None:
        if self._processes:
            raise NotImplementedError("worker processes are not made yet")
        call.run(through=round_trip)

    def _stop(self, wait: bool, cancel_futures: bool) -> None:
        """Stop nothing: an inline pool has no workers."""
