"""What the calls of a pool did, and a thread that notices when one holds the GIL."""

from __future__ import annotations

import logging
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, replace
from functools import partial
from typing import TYPE_CHECKING, Any, Final, final

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

POOL_OWNER: Final = "<pool>"

RUNNING: dict[int, tuple[str, str]] = {}
RUNNING_LOCK = threading.Lock()

logger = logging.getLogger("redsun")


@dataclass(frozen=True, slots=True)
class OwnerUsage:
    """What one owner's calls did in a pool."""

    queued: int
    """Calls waiting for a worker."""

    active: int
    """Calls running."""

    completed: int
    """Calls that returned."""

    failed: int
    """Calls that raised."""

    longest_idle: float
    """Seconds a call waited for a worker, the longest so far."""

    crashed: int = 0
    """Calls that failed because a worker process ended."""


EMPTY: Final = OwnerUsage(0, 0, 0, 0, 0.0)


class Counts:
    """Thread-safe call counts by owner."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._owners: dict[str, OwnerUsage] = {}

    def _bump(self, owner: str, waited: float = 0.0, **deltas: int) -> None:
        """Add *deltas* to the counts of *owner*, and raise its longest idle to *waited*."""
        with self._lock:
            now = self._owners.get(owner, EMPTY)
            self._owners[owner] = replace(
                now,
                longest_idle=max(now.longest_idle, waited),
                **{name: getattr(now, name) + delta for name, delta in deltas.items()},
            )

    def submitted(self, owner: str) -> None:
        """Count a call waiting for a worker."""
        self._bump(owner, queued=1)

    def started(self, owner: str, waited: float) -> None:
        """Move a call from waiting to running, after *waited* seconds."""
        self._bump(owner, waited, queued=-1, active=1)

    def unstarted(self, owner: str) -> None:
        """Move a call that never ran back from running to waiting."""
        self._bump(owner, queued=1, active=-1)

    def finished(self, owner: str, failed: bool) -> None:
        """Move a call from running to completed or failed."""
        self._bump(owner, active=-1, completed=not failed, failed=failed)

    def crashed(self, owner: str) -> None:
        """Count a call that failed because a worker process ended."""
        self._bump(owner, crashed=1)

    def dropped(self, owner: str) -> None:
        """Remove a waiting call that never ran."""
        self._bump(owner, queued=-1)

    def of(self, owner: str) -> OwnerUsage:
        """Return the counts of *owner*."""
        with self._lock:
            return self._owners.get(owner, EMPTY)

    def summary(self, label: str, pool_size: int) -> str:
        """Return one line on the calls made, such as `thread pool: 3 workers, ...`."""
        with self._lock:
            owners = dict(self._owners)
        calls = {name: u.completed + u.failed for name, u in owners.items()}
        by_owner = ", ".join(
            f"{name} {n}"
            for name, n in sorted(calls.items(), key=lambda item: -item[1])
            if n
        )
        failed = sum(u.failed for u in owners.values())
        longest = max((u.longest_idle for u in owners.values()), default=0.0)
        split = f" ({by_owner})" if by_owner else ""
        return (
            f"{label}: {pool_size} workers, {sum(calls.values())} calls{split},"
            f" {failed} failed, longest idle {longest:.1f} s"
        )


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


@contextmanager
def listed(fn: Callable[..., Any]) -> Generator[None, None, None]:
    """List *fn* as running in this thread, putting back the call it interrupted on exit."""
    ident = threading.get_ident()
    with RUNNING_LOCK:
        previous = RUNNING.get(ident)
        RUNNING[ident] = (threading.current_thread().name, label_of(fn))
    try:
        yield
    finally:
        with RUNNING_LOCK:
            if previous is None:
                del RUNNING[ident]
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
