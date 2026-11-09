"""Hand a future's result to a callback on the thread the callback names."""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, TypeVar

from psygnal import SignalInstance

from ..ports._wiring import marker_of

if TYPE_CHECKING:
    from collections.abc import Callable
    from concurrent.futures import Future

    from ..ports._wiring import SlotThread

R = TypeVar("R")

logger = logging.getLogger("redsun")

DRAINERS: set[object] = set()
"""The frontends draining the main-thread queue, which is where deliveries wait."""


def deliver(future: Future[R], callback: Callable[[R], object]) -> None:
    """Call *callback* with the result of *future* once it is done.

    When a slot-marked method names a thread, the call waits in `psygnal`'s
    queue until that thread calls `psygnal.emit_queued`; a callback without
    one is queued for the main thread. With no frontend draining the queue,
    the callback runs on the thread that finished the future. A failed
    future is logged and a cancelled one is not; neither calls the callback.
    """
    declared: SlotThread = getattr(marker_of(callback), "thread", None) or "main"
    thread = threading.current_thread() if declared == "current" else declared
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
            if DRAINERS:
                signal = SignalInstance((object,))
                signal.connect(callback, thread=thread)
                signal.emit(result)
            else:
                callback(result)
        except Exception:
            logger.exception("%s: the callback failed", name)

    future.add_done_callback(done)
