from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from ophyd_async.core import PathInfo, PathProvider, soft_signal_r_and_setter

if TYPE_CHECKING:
    from collections.abc import Callable

    from ophyd_async.core import SignalR


@dataclass(frozen=True, slots=True)
class PathSignals:
    base_dir: SignalR[str]
    plan: SignalR[str]


@dataclass(slots=True)
class _SignalSetters:
    base_dir: Callable[[str], None]
    plan: Callable[[str], None]


class SessionPathProvider(PathProvider):
    """Session-scoped path provider.

    Creates a per-session directory structure
    for file storage that allows devices
    to write files in their chosen format.

    Constructs a directory structure like:

    ```
    base_dir / session_name / plan_name / YYYY - MM - DD / plan_name_00001
    ```

    Parameters
    ----------
    base_dir : Path | None
        Base directory for storage. Defaults to `~/redsun-storage`.

        Note: `~` is expanded to the user's home directory.
    session : str | None
        Session name. Defaults to `"unknown-session"`.
    max_digits : int
        Zero-padding with for auto-increment counter. Defaults to 5 (e.g. `00001`).
    """

    __slots__ = (
        "_plan",
        "_session",
        "_base_dir",
        "_max_digits",
        "_date",
        "_signals",
        "_setters",
        "_counters",
        "_instance",
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
    ) -> None:
        self._plan = "unknown"
        self._session = session
        self._base_dir = base_dir or Path.home() / "redsun-storage"
        self._max_digits = max_digits
        self._date = datetime.now().strftime("%Y-%m-%d")

        base_dir_sig, base_dir_setter = soft_signal_r_and_setter(
            str, initial_value=str(self._base_dir)
        )
        plan_sig, plan_setter = soft_signal_r_and_setter(str, initial_value=self._plan)

        self._signals = PathSignals(base_dir=base_dir_sig, plan=plan_sig)
        self._setters = _SignalSetters(base_dir=base_dir_setter, plan=plan_setter)
        self._counters = dict[str, int]()
        self._scan_existing()

    def set_base_dir(self, base_dir: Path) -> None:
        """Change the base directory.

        Scan the existing files in the new root to update the counters for each plan.
        """
        self._setters.base_dir(str(base_dir))
        self._base_dir = base_dir
        self._scan_existing()

    def set_plan(self, plan: str) -> None:
        """Change the current plan name.

        Scan the existing files in the current root + session directory
        to update the counters for each plan.
        """
        self._setters.plan(plan)
        self._plan = plan
        self._scan_existing()

    def _scan_existing(self) -> None:
        """Scan the existing files in the current session directory to update the counters for each plan."""
        directory = self._base_dir / self._session
        if not directory.exists():
            return
        for plan_dir in directory.iterdir():
            if not plan_dir.is_dir():
                continue
            for date_dir in plan_dir.iterdir():
                if not date_dir.is_dir():
                    continue
                for entry in date_dir.iterdir():
                    parts = entry.stem.rsplit("_", 1)
                    if len(parts) != 2 or not parts[1].isdigit():
                        continue
                    key, suffix = parts
                    n = int(suffix)
                    if n + 1 > self._counters.get(key, 0):
                        self._counters[key] = n + 1

    def __call__(self, datakey_name: str | None = None) -> PathInfo:
        """Return a `PathInfo` object for the next file to be created.

        `datakey_name` is idempotent: it will not affect the
        returned path.
        """
        plan_count = self._counters.get(self._plan, 0)
        filename = f"{self._plan}_{plan_count:0{self._max_digits}d}"
        directory = self._base_dir / self._session / self._date
        directory.mkdir(parents=True, exist_ok=True)
        self._counters[self._plan] = plan_count + 1
        return PathInfo(directory_path=directory, filename=filename)
