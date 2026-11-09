"""Hand a future's result to a callback on the thread the callback names."""

from __future__ import annotations

import logging
import threading
import weakref
from typing import TYPE_CHECKING, TypeVar

from psygnal import SignalInstance

from ..ports._wiring import marker_of

if TYPE_CHECKING:
    from collections.abc import Callable
    from concurrent.futures import Future

    from ..ports._wiring import SlotThread

R = TypeVar("R")

logger = logging.getLogger("redsun")

DRAINERS: dict[object, threading.Thread] = {}
"""The frontends draining the main-thread queue, each with the thread it was built on."""

LOCK = threading.RLock()
"""Held while a result is queued and while a frontend stops draining.

A frontend that has stopped draining and then emptied the queue finds
nothing queued for it afterwards.
"""


def start_draining(drainer: object) -> None:
    """Queue the results delivered from now on until *drainer* stops draining.

    *drainer* is built on the calling thread, where a callback marked
    `"current"` runs.
    """
    with LOCK:
        DRAINERS[drainer] = threading.current_thread()


def stop_draining(drainer: object) -> None:
    """Drop the results that finish from now on for the deliveries made while *drainer* drained.

    What is queued already stays queued, for *drainer* to empty next.
    """
    with LOCK:
        DRAINERS.pop(drainer, None)


def deliver(future: Future[R], callback: Callable[[R], object]) -> None:
    """Call *callback* with the result of *future* once it is done.

    While a frontend drains the queue, the callback waits in `psygnal`'s
    queue until the thread its slot marker names calls `psygnal.emit_queued`;
    `"current"` names the thread the session was built on, as in wiring, and
    a callback naming no thread is queued for the main thread. A result that
    finishes once that frontend has shut down is dropped and logged at debug
    level. With no frontend draining when `deliver` is called, the callback
    runs on the thread that finished the future. A failed future is logged
    and a cancelled one is not; neither calls the callback.
    """
    declared: SlotThread = getattr(marker_of(callback), "thread", None) or "main"
    with LOCK:
        queued = bool(DRAINERS)
        # weak, so a call outliving its session does not keep the session alive
        drainers = weakref.WeakSet(DRAINERS)
        if declared == "current":
            declared = next(iter(DRAINERS.values()), threading.main_thread())
    name = getattr(callback, "__qualname__", callback)

    def done(finished: Future[R]) -> None:
        if finished.cancelled():
            logger.debug("%s: its computation was cancelled", name)
            return
        try:
            result = finished.result()
        except BaseException:
            logger.exception("%s: its computation failed", name)
            return
        try:
            if not queued:
                callback(result)
                return
            with LOCK:
                if drainers.isdisjoint(DRAINERS):
                    logger.debug("%s: its session has shut down", name)
                    return
                signal = SignalInstance((object,))
                signal.connect(callback, thread=declared)
                signal.emit(result)
        except BaseException as error:
            # anything but an Exception ends a pool thread for good
            main = threading.current_thread() is threading.main_thread()
            if main and not isinstance(error, Exception):
                raise
            logger.exception("%s: the callback failed", name)

    future.add_done_callback(done)
