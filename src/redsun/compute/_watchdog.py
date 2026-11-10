"""A thread that notices when a pool call holds the GIL."""

from __future__ import annotations

import threading
import time
from functools import partial
from typing import TYPE_CHECKING, final

from ._future import logger

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any

RUNNING: dict[int, tuple[str, str]] = {}
RUNNING_LOCK = threading.Lock()


def running() -> dict[str, str]:
    """Return the qualified name of the function each pool thread is running, by thread name."""
    with RUNNING_LOCK:
        return dict(RUNNING.values())


def label_of(fn: Callable[..., Any]) -> str:
    """Return the module and qualified name of *fn*, looking through `functools.partial`."""
    while isinstance(fn, partial):
        fn = fn.func
    name = getattr(fn, "__qualname__", None) or type(fn).__qualname__
    return f"{getattr(fn, '__module__', None) or '?'}.{name}"


def begin(fn: Callable[..., Any]) -> tuple[int, tuple[str, str] | None]:
    """Record *fn* as running in this thread; return the thread's id and what it replaced."""
    thread = threading.current_thread()
    entry = (thread.name, label_of(fn))
    with RUNNING_LOCK:
        previous = RUNNING.get(thread.ident or 0)
        RUNNING[thread.ident or 0] = entry
    return thread.ident or 0, previous


def end(ident: int, previous: tuple[str, str] | None) -> None:
    """Forget the call `begin` recorded, putting back the one it interrupted."""
    with RUNNING_LOCK:
        if previous is None:
            RUNNING.pop(ident, None)
        else:
            RUNNING[ident] = previous


@final
class Watchdog:
    """Logs the pool calls running while its thread woke later than a limit."""

    def __init__(self, *, period: float = 0.05, limit: float = 0.2) -> None:
        self._period = period
        self._limit = limit
        self._stopped = threading.Event()
        self._thread: threading.Thread | None = None
        self._reported: set[str] = set()

    def start(self) -> None:
        """Start the thread, once."""
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._watch, name="redsun-watchdog", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the thread and wait for it; does nothing when it never started."""
        self._stopped.set()
        if self._thread is not None:
            self._thread.join()

    def _watch(self) -> None:
        while True:
            before = time.monotonic()
            if self._stopped.wait(self._period):
                return
            late = time.monotonic() - before - self._period
            if late > self._limit:
                self._report(late)

    def _report(self, late: float) -> None:
        names = sorted(set(running().values()) - self._reported)
        if not names:
            return
        self._reported.update(names)
        logger.warning(
            f"A thread woke {late:.2f} s late while {', '.join(names)} ran in a pool: "
            "it may hold the GIL, which slows every other thread, the window's included"
        )
