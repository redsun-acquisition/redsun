from __future__ import annotations

import math
import time
from dataclasses import dataclass
from numbers import Real
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping


class PlanProgress:
    """A progress scope a plan declared, passing each update to its watchers.

    Watchers receive `name`, `current`, `initial`, `target`, `unit`,
    `precision`, `fraction`, `time_elapsed` and `time_remaining` as keywords.
    A fraction given alone is passed on as `current`, with `initial` 0 and
    `target` 1.
    """

    def __init__(self, name: str, *, parent: PlanProgress | None = None) -> None:
        self.name = name
        """Name the plan declared the scope under."""
        self.parent = parent
        """Scope this one is nested under, or `None`."""
        self._done = False
        self._watchers: list[Callable[..., None]] = []
        self._last_state: dict[str, Any] | None = None
        self._start_time = time.time()

    @property
    def done(self) -> bool:
        """Whether the scope has finished."""
        return self._done

    def watch(self, func: Callable[..., None]) -> None:
        """Pass every update to *func*, starting with the last one, if any."""
        self._watchers.append(func)
        if self._last_state is not None:
            func(**self._last_state)

    def _notify(
        self,
        *,
        current: Any = None,
        initial: Any = None,
        target: Any = None,
        unit: str = "unit",
        precision: Any = None,
        fraction: Any = None,
        time_elapsed: float | None = None,
        time_remaining: float | None = None,
    ) -> None:
        if (
            fraction is not None
            and current is None
            and initial is None
            and target is None
        ):
            current = fraction
            initial = 0
            target = 1
        if time_elapsed is None:
            time_elapsed = time.time() - self._start_time
        self._last_state = {
            "name": self.name,
            "current": current,
            "initial": initial,
            "target": target,
            "unit": unit,
            "precision": precision,
            "fraction": fraction,
            "time_elapsed": time_elapsed,
            "time_remaining": time_remaining,
        }
        for watcher in self._watchers:
            watcher(**self._last_state)

    def finish(self) -> None:
        """Mark the scope done, reporting it complete to the watchers once more."""
        self._done = True
        last = self._last_state
        if last is not None and last.get("target") is not None:
            self._notify(
                current=last["target"],
                initial=last["initial"],
                target=last["target"],
                unit=last["unit"],
                precision=last["precision"],
            )
        else:
            self._notify(fraction=1.0)


@dataclass(frozen=True, slots=True)
class ProgressState:
    """One progress scope of the running plan, as it stood when reported."""

    name: str
    """Name the plan declared the scope under."""

    parent: str | None
    """Name of the scope this one is nested under, or `None`."""

    current: float | None
    """How far the scope has got, in `unit`; `None` when the plan reported a fraction."""

    initial: float | None
    """Where the scope started, in `unit`."""

    target: float | None
    """Where the scope ends, in `unit`; `None` when the end is not known."""

    unit: str
    """What the scope counts, such as `frames`."""

    precision: int | None
    """Decimals to show `current` and `target` with; `None` for the shortest form."""

    fraction: float | None
    """How far the scope has got, from 0 to 1; `None` when it has no known end."""

    time_elapsed: float | None
    """Seconds since the scope was declared."""

    time_remaining: float | None
    """Seconds the plan expects the scope to take still."""


def number(value: object) -> float | None:
    """Return *value* as a float, or `None` when it is not a finite real number."""
    if isinstance(value, bool) or not isinstance(value, Real):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def depth(scope: PlanProgress) -> int:
    """Return how many scopes *scope* is nested under."""
    count = 0
    parent = scope.parent
    while parent is not None:
        count += 1
        parent = parent.parent
    return count


def empty_state(scope: PlanProgress) -> ProgressState:
    """Return the state of a scope declared but not yet updated."""
    parent = scope.parent.name if scope.parent is not None else None
    return ProgressState(
        scope.name, parent, None, None, None, "", None, None, None, None
    )


def snapshot(scope: PlanProgress, update: Mapping[str, Any]) -> ProgressState:
    """Return the state of *scope* after *update*, the keywords its watchers get.

    A reported fraction is taken as given, and the `current`, `initial` and
    `target` filled in from it are left out; otherwise the fraction is
    computed from those three when they are numbers spanning a range.
    """
    reported = number(update.get("fraction"))
    if reported is not None:
        current = initial = target = None
        fraction: float | None = min(max(reported, 0.0), 1.0)
    else:
        current = number(update.get("current"))
        initial = number(update.get("initial"))
        target = number(update.get("target"))
        fraction = None
        if (
            current is not None
            and initial is not None
            and target is not None
            and target != initial
        ):
            fraction = min(max((current - initial) / (target - initial), 0.0), 1.0)
    precision = update.get("precision")
    return ProgressState(
        name=scope.name,
        parent=scope.parent.name if scope.parent is not None else None,
        current=current,
        initial=initial,
        target=target,
        unit=str(update.get("unit", "unit")),
        precision=precision
        if isinstance(precision, int)
        and not isinstance(precision, bool)
        and precision >= 0
        else None,
        fraction=fraction,
        time_elapsed=number(update.get("time_elapsed")),
        time_remaining=number(update.get("time_remaining")),
    )
