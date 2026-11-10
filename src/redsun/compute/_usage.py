"""Per-owner counts of the calls a pool ran."""

from __future__ import annotations

import threading
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Mapping

POOL_OWNER: Final = "<pool>"


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


EMPTY: Final = OwnerUsage(0, 0, 0, 0, 0.0)


@dataclass(frozen=True, slots=True)
class Usage:
    """What a pool's calls did, in total and per owner."""

    pool_size: int
    """Threads, processes or devices."""

    active: int
    """Workers running a call now."""

    owners: Mapping[str, OwnerUsage]
    """Counts by owner name."""


class Counts:
    """Thread-safe call counts by owner."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._owners: dict[str, OwnerUsage] = {}

    def submitted(self, owner: str) -> None:
        """Count a call waiting for a worker."""
        with self._lock:
            now = self._owners.get(owner, EMPTY)
            self._owners[owner] = replace(now, queued=now.queued + 1)

    def started(self, owner: str, waited: float) -> None:
        """Move a call from waiting to running, after *waited* seconds."""
        with self._lock:
            now = self._owners.get(owner, EMPTY)
            self._owners[owner] = replace(
                now,
                queued=now.queued - 1,
                active=now.active + 1,
                longest_idle=max(now.longest_idle, waited),
            )

    def finished(self, owner: str, failed: bool) -> None:
        """Move a call from running to completed or failed."""
        with self._lock:
            now = self._owners.get(owner, EMPTY)
            self._owners[owner] = replace(
                now,
                active=now.active - 1,
                completed=now.completed + (not failed),
                failed=now.failed + failed,
            )

    def dropped(self, owner: str) -> None:
        """Remove a waiting call that never ran."""
        with self._lock:
            now = self._owners.get(owner, EMPTY)
            self._owners[owner] = replace(now, queued=now.queued - 1)

    def of(self, owner: str) -> OwnerUsage:
        """Return the counts of *owner*."""
        with self._lock:
            return self._owners.get(owner, EMPTY)

    def usage(self, pool_size: int) -> Usage:
        """Return the counts of every owner."""
        with self._lock:
            owners = dict(self._owners)
        active = sum(u.active for u in owners.values())
        return Usage(pool_size, active, owners)

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
