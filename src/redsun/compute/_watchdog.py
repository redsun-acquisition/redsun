"""A thread that notices when a pool call holds the GIL."""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING, final

from ._future import logger

if TYPE_CHECKING:
    from collections.abc import Callable
    from typing import Any

RUNNING: dict[str, str] = {}
RUNNING_LOCK = threading.Lock()


def running() -> dict[str, str]:
    """Return the qualified name of the function each pool thread is running, by thread name."""
    with RUNNING_LOCK:
        return dict(RUNNING)


def begin(fn: Callable[..., Any]) -> tuple[str, str | None]:
    """Record *fn* as running in this thread; return the thread name and what it replaced."""
    name = threading.current_thread().name
    label = getattr(fn, "__qualname__", None) or type(fn).__qualname__
    with RUNNING_LOCK:
        previous = RUNNING.get(name)
        RUNNING[name] = label
    return name, previous


def end(name: str, previous: str | None) -> None:
    """Forget the call `begin` recorded, putting back the one it interrupted."""
    with RUNNING_LOCK:
        if previous is None:
            RUNNING.pop(name, None)
        else:
            RUNNING[name] = previous


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
            "a function that holds the GIL belongs on a ProcessExecutor"
        )
