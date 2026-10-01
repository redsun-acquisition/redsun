from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Final, Literal

if TYPE_CHECKING:
    import pyinstrument

    from redsun.log import SessionFileHandler

ProfileKind = Literal["start", "run"]
"""What a session profiles: its start, up to its window, or its whole run."""

PROFILE_KINDS: Final = ("start", "run")
"""The values `Session` accepts for `profile`."""


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
    return SessionProfile(profile, profile_dir, pyinstrument.Profiler())


class SessionProfile:
    """A running profile of one session, written as HTML once stopped."""

    __slots__ = ("folder", "kind", "log", "profiler", "started")

    def __init__(
        self,
        kind: str,
        folder: str | Path | None,
        profiler: pyinstrument.Profiler,
    ) -> None:
        self.kind = kind
        self.folder = None if folder is None else Path(folder)
        self.log: SessionFileHandler | None = None
        self.started = datetime.now().astimezone()
        self.profiler = profiler
        self.profiler.start()

    def follow(self, log: SessionFileHandler) -> None:
        """Name the profile after the run *log* writes, and default to its root."""
        self.log = log

    def stop(self, session: str) -> None:
        """Stop profiling and write the profile; filled in by the next task."""
        if self.profiler.is_running:
            self.profiler.stop()
