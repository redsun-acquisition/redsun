"""Where a session's acquisition files go.

Paths are `<base_dir>/<session>/<YYYY-MM-DD>/<datakey>/<plan>_<counter>`,
`base_dir` defaulting to the user data directory. The container builds one
provider per session and passes it to every device taking a ``path_provider``
keyword.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final

from ophyd_async.core import FilenameProvider, PathInfo, PathProvider
from platformdirs import user_data_dir
from psygnal import Signal

from redsun.experimental.ports import slot

from .utils._paths import session_folder

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

__all__ = [
    "PATH_PROVIDER_PORT",
    "PlanFilenameProvider",
    "SessionPathProvider",
    "session_directory",
]

_RESET_PLAN = "unknown"


def _base_dir() -> Path:
    return Path(user_data_dir("redsun", appauthor=False))


def session_directory(session: str) -> Path:
    """Return *session*'s directory under the default root.

    Named as `SessionPathProvider.session_dir` names it.
    """
    return _base_dir() / session_folder(session)


class PlanFilenameProvider(FilenameProvider):
    """Filenames with a counter per plan.

    Filenames are `<plan_name>_<counter>`, zero-padded to `max_digits`. Each
    data key counts on its own; its directory tells two detectors apart.

    Parameters
    ----------
    max_digits : int
        Zero-padding width of the counter, as in `00001` for 5.
    """

    __slots__ = ("_counters", "_max_digits", "_plan")

    @property
    def plan(self) -> str:
        """The current plan name."""
        return self._plan

    @property
    def max_digits(self) -> int:
        """Zero-padding width of the counter."""
        return self._max_digits

    def __init__(self, *, max_digits: int = 5) -> None:
        self._plan = "unknown"
        self._max_digits = max_digits
        self._counters: dict[tuple[str, str], int] = {}

    def set_plan(self, plan: str) -> None:
        """Change the current plan name."""
        self._plan = plan

    def reset(self, counters: Mapping[tuple[str, str], int]) -> None:
        """Replace every counter, as after a base directory change."""
        self._counters = dict(counters)

    def bump(self, plan: str, datakey_name: str, next_count: int) -> None:
        """Raise the counter for a plan and data key to at least `next_count`."""
        key = (plan, datakey_name)
        if next_count > self._counters.get(key, 0):
            self._counters[key] = next_count

    def __call__(self, datakey_name: str | None = None) -> str:
        """Return the next, never repeated, filename for the plan and *datakey_name*."""
        key = (self._plan, datakey_name or "")
        count = self._counters.get(key, 0)
        self._counters[key] = count + 1
        return f"{self._plan}_{count:0{self._max_digits}d}"


class SessionPathProvider(PathProvider):
    """Path provider for one session.

    Paths have the layout:

    ```
    base_dir / session_name / YYYY-MM-DD / datakey / <plan>_<counter>{.ext}
    ```

    The data key is the one the caller asks with, so each detector writes into
    a directory of its own and owns its store. A call without one leaves that
    level out.

    The date is read on each request, not at construction. The counter belongs
    to `(session, plan, datakey)` and only increases: date directories group
    files but do not reset the counter.

    Parameters
    ----------
    base_dir : Path | None
        Base directory, with `~` expanded. Defaults to the user data
        directory, as `session_directory` gives it.
    session : str
        Session name, fixed for the provider's lifetime.
    max_digits : int
        Zero-padding width of the counter, as in `00001` for 5.
    now: Callable[[], datetime] | None
        Clock giving the date directory, for tests. Defaults to `datetime.now`.
    """

    sig_base_dir_changed = Signal(Path)
    """Emitted with the new root once `set_base_dir` accepted it."""

    __slots__ = (
        "_base_dir",
        "_base_dir_lock",
        "_filenames",
        "_now",
        "_pattern",
        "_session",
    )

    def __init__(
        self,
        *,
        base_dir: Path | None = None,
        session: str = "unknown-session",
        max_digits: int = 5,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._session = session
        self._base_dir = (base_dir or _base_dir()).expanduser()
        self._base_dir_lock: str | None = None
        self._filenames = PlanFilenameProvider(max_digits=max_digits)
        self._now = now or datetime.now

        self._pattern = re.compile(
            rf"^(?P<plan>.+)_(?P<count>\d{{{max_digits}}})(?:-.*)?$"
        )

        self._scan_existing()

    @property
    def base_dir(self) -> Path:
        """Root the session's files go under."""
        return self._base_dir

    @property
    def session_dir(self) -> Path:
        """Directory inside `base_dir` holding the session's files.

        Named after the session, each run of characters other than letters,
        digits, `.`, `-` and `_` replaced by `_` and outer dots removed.
        """
        return self._base_dir / session_folder(self._session)

    @slot
    def set_base_dir(self, base_dir: str | Path) -> None:
        """Change the base directory from the next request on, rescanning counters.

        Raises
        ------
        RuntimeError
            If `lock_base_dir` was called, or a plan is running. A session not
            wiring `set_plan` and `reset_plan` cannot tell a plan is running.
        """
        if self._base_dir_lock is not None:
            raise RuntimeError(
                f"The base directory cannot change: {self._base_dir_lock}."
            )
        if self._filenames.plan != _RESET_PLAN:
            raise RuntimeError(
                f"Plan {self._filenames.plan!r} is running; changing the base "
                "directory now would split its files across two roots. Change "
                "it between runs."
            )
        self._base_dir = Path(base_dir).expanduser()
        self._filenames.reset({})
        self._scan_existing()
        self.sig_base_dir_changed.emit(self._base_dir)

    def lock_base_dir(self, reason: str) -> None:
        """Refuse every later `set_base_dir`, giving *reason* in the error."""
        self._base_dir_lock = reason

    @slot
    def set_plan(self, plan: str) -> None:
        """Change the active plan name."""
        self._filenames.set_plan(plan)

    @slot
    def reset_plan(self) -> None:
        """Set the plan name back to its placeholder, rescanning counters.

        A filename requested by the plan and never written returns to the
        pool, so the next plan continues from what is on disk.
        """
        self._filenames.set_plan(_RESET_PLAN)
        self._filenames.reset({})
        self._scan_existing()

    def _scan_existing(self) -> None:
        """Set each `(plan, datakey)` counter one past the highest number on disk."""
        directory = self.session_dir
        if not directory.exists():
            return
        for date_dir in directory.iterdir():
            if not date_dir.is_dir():
                continue
            for entry in date_dir.iterdir():
                # a store can be a directory, as a Zarr one is, so an entry
                # counts as a data key's only when its name does not parse
                if self._bump_from(entry, datakey_name="") or not entry.is_dir():
                    continue
                for nested in entry.iterdir():
                    self._bump_from(nested, datakey_name=entry.name)

    def _bump_from(self, entry: Path, *, datakey_name: str) -> bool:
        """Raise *datakey_name*'s counter past *entry*, and say whether it did."""
        # everything after the first dot is suffix: scan_00004.ome.zarr is
        # scan_00004, where Path.stem would keep scan_00004.ome
        match = self._pattern.match(entry.name.split(".", 1)[0])
        if match is None:
            return False
        self._filenames.bump(
            match.group("plan"), datakey_name, int(match.group("count")) + 1
        )
        return True

    def __call__(self, datakey_name: str | None = None) -> PathInfo:
        """Return the `PathInfo` of the next file for *datakey_name*.

        Each call returns a new path, since it increments that data key's
        counter for the active plan.
        """
        directory = self.session_dir / self._now().strftime("%Y-%m-%d")
        if datakey_name:
            directory = directory / datakey_name
        return PathInfo(
            directory_path=directory, filename=self._filenames(datakey_name)
        )


PATH_PROVIDER_PORT: Final = "path_provider"
"""Name the session's path provider is wired under."""
