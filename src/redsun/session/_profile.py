from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal

from platformdirs import user_data_dir

from redsun.log import LOG_RUNS_KEPT

from ..utils._paths import session_folder

if TYPE_CHECKING:
    import pyinstrument

    from redsun.log import SessionFileHandler

ProfileKind = Literal["start", "run"]
"""What a session profiles: its start, up to its window, or its whole run."""

PROFILE_KINDS: Final = ("start", "run")
"""The values `Session` accepts for `profile`."""

logger = logging.getLogger("redsun")


def open_profile(
    profile: str | None, profile_dir: str | Path | None
) -> SessionProfile | None:
    """Start profiling a session as *profile* asks, or return `None` when it asks nothing.

    Raises
    ------
    ValueError
        If *profile* is not one of `PROFILE_KINDS`.
    TypeError
        If *profile_dir* is given without *profile*.
    ImportError
        If `pyinstrument`, from the `profile` extra, is not installed.
    """
    if profile is None:
        if profile_dir is not None:
            raise TypeError("profile_dir is given without profile")
        return None
    if profile not in PROFILE_KINDS:
        known = ", ".join(map(repr, PROFILE_KINDS))
        raise ValueError(f"profile is {profile!r}; expected one of {known}")
    try:
        import pyinstrument  # noqa: PLC0415
    except ImportError as e:
        raise ImportError(
            "profiling a session needs pyinstrument: install redsun[profile]"
        ) from e
    folder = None if profile_dir is None else Path(profile_dir)
    return SessionProfile(profile, folder, pyinstrument.Profiler())


@dataclass(slots=True, eq=False)
class SessionProfile:
    """A running profile of one session, written as HTML once stopped."""

    kind: str
    """What the session profiles, one of `PROFILE_KINDS`."""

    folder: Path | None
    """Folder the profile is written to; `None` for the one beside the logs."""

    profiler: pyinstrument.Profiler
    """The profiler; `start` starts it."""

    log: SessionFileHandler | None = None
    """The run's log file handler, which names the profile once followed."""

    started: datetime = field(default_factory=lambda: datetime.now().astimezone())
    """When the profile started, naming it when no log file was opened."""

    def start(self) -> None:
        """Start sampling the thread this is called on."""
        self.profiler.start()

    def follow(self, log: SessionFileHandler) -> None:
        """Name the profile after the run *log* writes, and default to its root."""
        self.log = log

    def target(self, session: str) -> Path:
        """Return the file the profile is written to.

        Named after the run the log file records, or after this profile's
        start when the session opened no log file. The folder is the one
        given, or `profiles/<session>` beside the session's logs.
        """
        if self.log is not None:
            run, root = self.log.run, self.log.root
        else:
            stamp = self.started.strftime("%Y-%m-%dT%H-%M-%S")
            run = f"{stamp}_{os.getpid()}"
            root = Path(user_data_dir("redsun", appauthor=False))
        folder = self.folder or root / "profiles" / session_folder(session)
        return folder / f"{run}.html"

    def stop(self, session: str) -> None:
        """Stop profiling and write the profile, once.

        A failure to stop or to write is logged rather than raised.
        """
        if not self.profiler.is_running:
            return
        path = self.target(session)
        try:
            self.profiler.stop()
            path.parent.mkdir(parents=True, exist_ok=True)
            self.profiler.write_html(path, timeline=True)
        except Exception as e:  # noqa: BLE001
            # a profile is a diagnostic: failing to make one must not end or
            # fail the session it describes
            logger.error("Could not write the profile to %s: %s", path, e)
            return
        logger.info("Profile written to %s", path)
        if self.folder is None:
            delete_old_profiles(path.parent, keep=LOG_RUNS_KEPT)


def delete_old_profiles(folder: Path, keep: int) -> None:
    """Delete every profile in *folder* but the *keep* most recent."""
    written = sorted(folder.glob("*.html"))
    for path in written[: max(len(written) - keep, 0)]:
        path.unlink(missing_ok=True)
