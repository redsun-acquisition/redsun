"""The future a pool returns."""

from __future__ import annotations

import concurrent.futures
import logging
import traceback
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, TypeVar

from psygnal import SignalInstance

from ..ports._wiring import marker_of

if TYPE_CHECKING:
    import threading
    from collections.abc import Callable

    from ..ports._wiring import SlotThread

R = TypeVar("R")

PRE_START: Final = "the pool starts after every setup; use .then(...)"

logger = logging.getLogger("redsun")


def trace(error: BaseException) -> str:
    """Return *error* and its traceback as text."""
    return "".join(traceback.format_exception(error))


class BrokenPool(concurrent.futures.BrokenExecutor):
    """Raised by a call whose pool stopped working before it could run."""


class WorkerCrashed(Exception):
    """Raised by a call that was unfinished when a worker process ended."""


@dataclass(frozen=True, slots=True)
class Delivery:
    """Where a future's callbacks run."""

    thread: SlotThread
    """Thread a callback runs on when it names none."""

    session_thread: threading.Thread | None
    """The thread `"current"` stands for."""


def target_thread(
    delivery: Delivery | None, on_result: Callable[[Any], object]
) -> SlotThread:
    """Return the thread to run *on_result* on, `None` to run it where the call finished."""
    if delivery is None:
        return None
    marker = marker_of(on_result)
    target = (marker.thread if marker else None) or delivery.thread
    return delivery.session_thread if target == "current" else target


class Future(concurrent.futures.Future[R]):
    """A call's result, delivered by [`then`][redsun.compute.Future.then]."""

    def __init__(self) -> None:
        super().__init__()
        self._owner = ""
        self._delivery: Delivery | None = None
        self._released: Callable[[], bool] = lambda: False
        self._queued = False
        self._linked: concurrent.futures.Future[Any] | None = None
        self._handing_over = False

    def cancel(self) -> bool:
        """Cancel the call, unless a worker has taken it."""
        with self._condition:
            linked = self._linked
            if linked is None and self._handing_over:
                return False
        if linked is not None and not linked.cancel():
            return False
        return super().cancel()

    def _hand_over(self) -> bool:
        """Refuse cancels from now on, unless the call is already cancelled."""
        with self._condition:
            if self.cancelled():
                return False
            self._handing_over = True
            return True

    def _link(
        self,
        standard: concurrent.futures.Future[Any] | None,
        on_link: Callable[[], object] = lambda: None,
    ) -> None:
        """End the hand-over: link the future of the worker running the call and call *on_link*.

        With no *standard*, the hand-over failed and cancels work again.
        """
        with self._condition:
            self._linked = standard
            self._handing_over = False
            on_link()

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

            target = target_thread(future._delivery, on_result)
            if target is None:
                call()
                return
            relay = SignalInstance((object,))
            relay.connect(call, thread=target)
            relay.emit(None)
            relay.disconnect()

        self.add_done_callback(deliver)
