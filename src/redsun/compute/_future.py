"""The future a pool returns."""

from __future__ import annotations

import concurrent.futures
import logging
import traceback
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, TypeVar

from psygnal import SignalInstance

from ..ports._wiring import marker_of

if TYPE_CHECKING:
    import threading
    from collections.abc import Callable

    from ..ports._wiring import SlotThread

R = TypeVar("R")

PRE_START: Final = "the pool starts after every setup; use .then(...)"

logger = logging.getLogger("redsun.compute")


def trace(error: BaseException) -> str:
    """Return *error* and its traceback as text."""
    return "".join(traceback.format_exception(error))


class BrokenPool(concurrent.futures.BrokenExecutor):
    """Raised by a call whose pool stopped working before it could run."""


@dataclass(frozen=True, slots=True)
class Delivery:
    """Where a future's callbacks run."""

    thread: SlotThread
    """Thread a callback runs on when it names none."""

    session_thread: threading.Thread | None
    """The thread `"current"` stands for."""


class Future(concurrent.futures.Future[R]):
    """A call's result, delivered by [`then`][redsun.compute.Future.then]."""

    def __init__(self) -> None:
        super().__init__()
        self._owner = ""
        self._delivery: Delivery | None = None
        self._released: Callable[[], bool] = lambda: False
        self._queued = False

    def _bind(
        self, owner: str, delivery: Delivery | None, released: Callable[[], bool]
    ) -> None:
        self._owner = owner
        self._delivery = delivery
        self._released = released

    def _mark_queued(self, queued: bool) -> None:
        self._queued = queued

    def _refuse_before_start(self, timeout: float | None) -> None:
        if self._queued and timeout is None and not self.done():
            raise RuntimeError(PRE_START)

    def result(self, timeout: float | None = None) -> R:
        """Return the result, refusing to wait without a timeout before the pool starts."""
        self._refuse_before_start(timeout)
        return super().result(timeout)

    def exception(self, timeout: float | None = None) -> BaseException | None:
        """Return the exception, refusing to wait without a timeout before the pool starts."""
        self._refuse_before_start(timeout)
        return super().exception(timeout)

    def then(
        self,
        on_result: Callable[[R], object],
        on_error: Callable[[BaseException], object] | None = None,
    ) -> None:
        """Call `on_result` with the result, or `on_error` with the exception.

        The callback runs on the thread it is marked with `slot`, else on the
        pool's delivery thread. A future of a pool with no delivery, or no
        pool, calls back in the thread that finishes the call. A cancelled
        call calls neither, and a failure with no `on_error` is logged.
        """
        name = getattr(on_result, "__qualname__", repr(on_result))

        def deliver(future: concurrent.futures.Future[R]) -> None:
            assert isinstance(future, Future)
            if future.cancelled():
                logger.debug(f"Call before {name} was cancelled")
                return

            def call() -> None:
                if future._released():
                    logger.debug(
                        f"Dropping the result for {name}: {future._owner} is gone"
                    )
                    return
                error = future.exception()
                try:
                    if error is None:
                        on_result(future.result())
                    elif on_error is not None:
                        on_error(error)
                    else:
                        logger.error(f"Call before {name} failed: {trace(error)}")
                except Exception as e:  # noqa: BLE001 - a failing callback must not stop the delivery of others
                    logger.error(f"Callback {name} raised: {trace(e)}")

            delivery = future._delivery
            if delivery is None:
                call()
                return
            marker = marker_of(on_result)
            target = (marker.thread if marker else None) or delivery.thread
            if target == "current":
                target = delivery.session_thread
            if target is None:
                call()
                return
            relay = SignalInstance((object,))
            relay.connect(call, thread=target)
            relay.emit(None)
            relay.disconnect()

        self.add_done_callback(deliver)
