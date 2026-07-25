from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from ophyd_async.core import (
    FilenameProvider,
    PathInfo,
    PathProvider,
    soft_signal_r_and_setter,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from ophyd_async.core import SignalR


@dataclass(frozen=True, slots=True)
class PathSignals:
    base_dir: SignalR[str]
    plan: SignalR[str]


@dataclass(slots=True)
class _SignalSetters:
    base_dir: Callable[[str], None]
    plan: Callable[[str], None]


class PlanFilenameProvider(FilenameProvider):
    """Provides auto-incrementing filenames scoped per plan.

    Templated as `<plan_name>_<counter>`, where `counter`
    is zero-padded to `max_digits`. Backends deriving
    per-key files must append their suffix with `-`
    (e.g. `plan_00003-camera`) so the counter remains
    parseable.

    Parameters
    ----------
    max_digits : int
        Zero-padding with for the counter.

        Defaults to 5 (e.g. `00001`).
    """

    __slots__ = ("_counters", "_max_digits", "_plan")

    @property
    def plan(self) -> str:
        """The current plan name."""
        return self._plan

    @property
    def max_digits(self) -> int:
        """The maximum number of digits for the counter."""
        return self._max_digits

    def __init__(self, *, max_digits: int = 5) -> None:
        self._plan = "unknown"
        self._max_digits = max_digits
        self._counters: dict[str, int] = {}

    def set_plan(self, plan: str) -> None:
        """Change the current plan name."""
        self._plan = plan

    def reset(self, counters: Mapping[str, int]) -> None:
        """Replace the counters wholesale (e.g. after a base directory change)."""
        self._counters = dict(counters)

    def bump(self, plan: str, next_count: int) -> None:
        """Raise the counter for a plan to at least `next_count`."""
        if next_count > self._counters.get(plan, 0):
            self._counters[plan] = next_count

    def __call__(self, datakey_name: str | None = None) -> str:
        """Return the next filename for the active plan.

        Each call uses up the current counter value and increments it,
        so the same filename is never returned twice.

        `datakey_name` is ignored: per-key naming is the responsibility of the backend.
        """
        count = self._counters.get(self._plan, 0)
        self._counters[self._plan] = count + 1
        return f"{self._plan}_{count:0{self._max_digits}d}"


class SessionPathProvider(PathProvider):
    """Session-scoped path provider.

    Computes path in the canonical layout:

    ```
    base_dir / session_name / YYYY-MM-DD/ <plan>_<counter>{.ext}
    ```

    where the date is evaluated when a path is requested (not when
    the provider is constructed) and the counter only ever increases,
    per `(session, plan)`, *across* dates: the date
    directory groups files, it does not scope the counter.

    Parameters
    ----------
    base_dir : Path | None
        Base directory for storage. Defaults to `~/redsun-storage`.

        Note: `~` is expanded to the user's home directory.
    session : str
        Session name. Fixed for the provider's lifetime.

        Defaults to `"unknown-session"`.
    max_digits : int
        Zero-padding with for auto-increment counter.

        Defaults to 5 (e.g. `00001`).
    now: Callable[[], datetime] | None
        Clock used to compute the date directory. For testing.

        Defaults to `datetime.now`.
    """

    __slots__ = (
        "_base_dir",
        "_filenames",
        "_now",
        "_pattern",
        "_session",
        "_setters",
        "_signals",
    )

    @property
    def signals(self) -> PathSignals:
        return self._signals

    def __init__(
        self,
        *,
        base_dir: Path | None = None,
        session: str = "unknown-session",
        max_digits: int = 5,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._session = session
        self._base_dir = (base_dir or Path.home() / "redsun-storage").expanduser()
        self._filenames = PlanFilenameProvider(max_digits=max_digits)
        self._now = now or datetime.now

        self._pattern = re.compile(
            rf"^(?P<plan>.+)_(?P<count>\d{{{max_digits}}})(?:-.*)?$"
        )

        base_dir_sig, base_dir_setter = soft_signal_r_and_setter(
            str, initial_value=str(self._base_dir)
        )
        plan_sig, plan_setter = soft_signal_r_and_setter(
            str, initial_value=self._filenames.plan
        )

        self._signals = PathSignals(base_dir=base_dir_sig, plan=plan_sig)
        self._setters = _SignalSetters(base_dir=base_dir_setter, plan=plan_setter)
        self._scan_existing()

    def set_base_dir(self, base_dir: Path) -> None:
        """Change the base directory, resetting and rescanning all counters."""
        self._base_dir = base_dir.expanduser()
        self._setters.base_dir(str(self._base_dir))
        self._filenames.reset({})
        self._scan_existing()

    def set_plan(self, plan: str) -> None:
        """Change the active plan name."""
        self._filenames.set_plan(plan)
        self._setters.plan(plan)

    def _scan_existing(self) -> None:
        """Recover per-plan counters from files under the session directory.

        Walks every date directory and raises each plan's counter to one
        past the highest number found, so newly generated filenames never
        reuse a number already present on disk.
        """
        directory = self._base_dir / self._session
        if not directory.exists():
            return
        for date_dir in directory.iterdir():
            if not date_dir.is_dir():
                continue
            for entry in date_dir.iterdir():
                match = self._pattern.match(entry.stem)
                if match is None:
                    continue
                self._filenames.bump(match.group("plan"), int(match.group("count")) + 1)

    def __call__(self, datakey_name: str | None = None) -> PathInfo:
        """Create the `PathInfo` for the next burst, ticking the plan counter.

        Each call produces a new, unique path: the active plan's counter
        value is used up and incremented.
        """
        directory = self._base_dir / self._session / self._now().strftime("%Y-%m-%d")
        return PathInfo(directory_path=directory, filename=self._filenames())
