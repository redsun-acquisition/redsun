from __future__ import annotations

import time
from dataclasses import asdict, replace
from typing import TYPE_CHECKING, Any, Generic

from ophyd_async.core import WatcherUpdate
from typing_extensions import TypeVar

if TYPE_CHECKING:
    from ophyd_async.core import Watcher

T = TypeVar("T", default=Any)


class PlanProgress(Generic[T]):
    """A progress scope a plan declared, passing each update to its watchers.

    Watchers receive the fields of a `WatcherUpdate` as keywords, as the
    watchers of an `ophyd-async` `WatchableAsyncStatus` do. `name` is always
    the name of the scope.
    """

    def __init__(self, name: str, *, parent: PlanProgress[Any] | None = None) -> None:
        self.name = name
        """Name the plan declared the scope under."""
        self.parent = parent
        """Scope this one is nested under, or `None`."""
        self._done = False
        self._watchers: list[Watcher[T]] = []
        self._update: WatcherUpdate[T | None] | None = None
        self._start = time.monotonic()

    @property
    def done(self) -> bool:
        """Whether the scope has finished."""
        return self._done

    @property
    def update(self) -> WatcherUpdate[T | None] | None:
        """The last update, or `None` before the first."""
        return self._update

    def watch(self, watcher: Watcher[T]) -> None:
        """Pass every update to *watcher*, starting with the last one, if any."""
        self._watchers.append(watcher)
        if self._update is not None:
            watcher(**asdict(self._update))

    def _notify(self, update: WatcherUpdate[T | None]) -> None:
        if update.time_elapsed is None:
            update = replace(update, time_elapsed=time.monotonic() - self._start)
        self._update = replace(update, name=self.name)
        for watcher in self._watchers:
            watcher(**asdict(self._update))

    def finish(self) -> None:
        """Mark the scope done, reporting it complete to the watchers once more."""
        self._done = True
        last = self._update
        if last is not None and last.target is not None:
            self._notify(
                WatcherUpdate(
                    current=last.target,
                    initial=last.initial,
                    target=last.target,
                    unit=last.unit,
                    precision=last.precision,
                )
            )
        else:
            self._notify(
                WatcherUpdate[T | None](
                    current=None, initial=None, target=None, fraction=1.0
                )
            )


def depth(scope: PlanProgress[Any]) -> int:
    """Return how many scopes *scope* is nested under."""
    count = 0
    parent = scope.parent
    while parent is not None:
        count += 1
        parent = parent.parent
    return count
