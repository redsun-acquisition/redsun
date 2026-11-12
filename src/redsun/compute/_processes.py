"""A pool of worker processes, and the executor that submits to it."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, final

from ._pickling import check_function, round_trip
from ._pool import Pool, PoolExecutor

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from ._future import Delivery
    from ._pool import Call
    from ._settings import Limits, Priority, ProcessPoolSettings


@final
class ProcessPool(Pool):
    """Worker processes several executors share; with `workers=0` a call runs where it is submitted.

    A call runs in a worker only if its function and arguments survive
    pickling. A function defined at module level of an importable module is
    sent by name; a lambda, a closure, a bound method or a function defined in
    the script being run is refused at `submit`. With `workers=0` each call
    and its result still make a pickle round trip.

    Parameters
    ----------
    workers
        Worker processes; 0 runs each call in the thread that submits it.
    priority
        The priority the workers start at.
    stop_timeout
        Seconds `shutdown` waits for running calls before ending the workers.
    log_name
        Name of the logger the workers' records are filed under.
    """

    def __init__(
        self,
        workers: int = 1,
        *,
        priority: Priority = "normal",
        stop_timeout: float = 10.0,
        log_name: str = "redsun.workers",
    ) -> None:
        super().__init__()
        self._workers = workers
        self._priority = priority
        self._stop_timeout = stop_timeout
        self._log_name = log_name

    @classmethod
    def resource(
        cls,
        settings: ProcessPoolSettings,
        limits: Limits,
        delivery: Delivery | None = None,
        owner: str = "<pool>",
    ) -> Generator[ProcessPool, None, None]:
        """Build a pool from *settings*, yield it unstarted, and stop it at teardown."""
        raise NotImplementedError

    @property
    def pool_size(self) -> int:
        """Worker processes."""
        return self._workers

    def _check(self, fn: Callable[..., Any]) -> None:
        check_function(fn)

    def _start(self) -> None:
        if self._workers:
            raise NotImplementedError("worker processes are not started yet")

    def _dispatch(self, call: Call[Any]) -> None:
        call.run(through=round_trip)

    def _stop(self, wait: bool, cancel_futures: bool) -> None:
        """Stop the workers; an inline pool has none."""


@final
class ProcessExecutor(PoolExecutor[ProcessPool]):
    """Runs one owner's calls on a shared pool of worker processes."""
