"""A session profiles its start or its whole run when asked, and refuses what it cannot do."""

from __future__ import annotations

import logging
import re
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

import pyinstrument
import pytest

from redsun import AsPresenter, BuildError, ConfigurationError, Session
from redsun.log import LOG_RUNS_KEPT, session_log

if TYPE_CHECKING:
    from redsun.testing import BuildSession

BUILD_PAUSE = 0.05
"""Seconds a component's constructor takes, so the profiler samples it."""


def wait_while_building() -> None:
    time.sleep(BUILD_PAUSE)


class Slow:
    """Presenter whose construction the profile must show."""

    def __init__(self, name: str) -> None:
        self.name = name
        wait_while_building()


class Broken:
    """Presenter that takes its time, then cannot be made."""

    def __init__(self, name: str) -> None:
        wait_while_building()
        raise ValueError("this presenter cannot be made")


class Empty(Session):
    pass


class Profiled(Session):
    slow: AsPresenter[Slow]


class FailsToBuild(Session):
    broken: AsPresenter[Broken]


class Unreadable(Session):
    config: ClassVar[dict[str, Any]] = {"schema_version": "not a number"}


def profiles(folder: Path) -> list[Path]:
    return sorted(folder.glob("*.html"))


@pytest.mark.parametrize(
    ("keywords", "error", "message"),
    [
        ({"profile": "Start"}, ValueError, "'start', 'run'"),
        ({"profile": "always"}, ValueError, "'start', 'run'"),
        ({"profile_dir": "profiles"}, TypeError, "given without profile"),
    ],
)
def test_a_profile_the_session_cannot_take_is_refused(
    keywords: dict[str, str], error: type[Exception], message: str
) -> None:
    """Refuse an unknown profile kind, and a profile folder with no profile."""
    with pytest.raises(error, match=message):
        Empty(**keywords)  # type: ignore[arg-type]


def test_a_profile_without_the_extra_names_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """Refuse a profile when `pyinstrument` is missing, naming the extra."""
    monkeypatch.setitem(sys.modules, "pyinstrument", None)

    with pytest.raises(ImportError, match=r"redsun\[profile\]"):
        Empty(profile="start")


def test_a_start_profile_shows_the_build_and_pairs_with_the_log(
    build: BuildSession, tmp_path: Path
) -> None:
    """Write a start profile at the end of the build, named like the run's log file."""
    app = build(Profiled(profile="start", profile_dir=tmp_path / "profiles"))

    written = profiles(tmp_path / "profiles")
    log = session_log()
    assert log is not None
    assert [path.name for path in written] == [f"{log.run}.html"]
    assert "wait_while_building" in written[0].read_text(encoding="utf-8")
    app.shutdown()
    assert profiles(tmp_path / "profiles") == written


def test_a_run_profile_is_written_once_at_shutdown(tmp_path: Path) -> None:
    """Write a run profile when the session shuts down, and only once."""
    app = Profiled(profile="run", profile_dir=tmp_path / "profiles").build()
    assert profiles(tmp_path / "profiles") == []

    app.shutdown()
    written = profiles(tmp_path / "profiles")
    app.shutdown()

    assert len(written) == 1
    assert profiles(tmp_path / "profiles") == written


def test_a_build_that_fails_still_writes_its_profile(tmp_path: Path) -> None:
    """Write the profile of a strict build that raises before the exception leaves."""
    session = FailsToBuild({"strict": True}, profile="start", profile_dir=tmp_path)

    with pytest.raises(BuildError):
        session.build()

    (written,) = profiles(tmp_path)
    assert "wait_while_building" in written.read_text(encoding="utf-8")


def test_a_profile_without_a_log_file_is_named_from_its_start(tmp_path: Path) -> None:
    """Name a profile from its start time when the session never opened a log file."""
    session = Unreadable(profile="start", profile_dir=tmp_path)

    with pytest.raises(ConfigurationError):
        session.build()

    (written,) = profiles(tmp_path)
    assert re.fullmatch(r"\d{4}(-\d{2}){2}T\d{2}(-\d{2}){2}_\d+\.html", written.name)


def test_the_default_folder_keeps_the_most_recent_profiles(
    build: BuildSession,
) -> None:
    """Keep the latest profiles beside the logs, deleting older ones."""
    app = build(Profiled(profile="run"))
    log = session_log()
    assert log is not None
    folder = log.root / "profiles" / "Profiled"
    folder.mkdir(parents=True)
    for second in range(25):
        old = folder / f"2000-01-01T00-00-{second:02d}_1.html"
        old.write_text("old", encoding="utf-8")

    app.shutdown()

    kept = profiles(folder)
    assert len(kept) == LOG_RUNS_KEPT
    assert kept[-1].name == f"{log.run}.html"


def test_a_profile_that_cannot_be_written_is_logged_and_the_session_runs(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Log a profile that cannot be written, and still build and shut down."""
    blocker = tmp_path / "taken"
    blocker.write_text("a file, not a folder", encoding="utf-8")
    app = Profiled(profile="start", profile_dir=blocker).build()

    app.shutdown()

    assert any(
        r.levelno == logging.ERROR and "profile" in r.getMessage()
        for r in caplog.records
    )


def test_a_session_from_a_file_takes_its_profile(tmp_path: Path) -> None:
    """Write the profile of a session made with `from_config`."""
    app = Session.from_config(
        {"session": "from-file"}, profile="start", profile_dir=tmp_path
    )
    app.build()
    app.shutdown()

    assert len(profiles(tmp_path)) == 1


def test_a_refused_log_level_leaves_no_profiler_running(tmp_path: Path) -> None:
    """Start no profiler when the session is refused, so the next one can profile."""
    with pytest.raises(ValueError):
        Empty(log_level="verbose", profile="run", profile_dir=tmp_path)

    app = Profiled(profile="start", profile_dir=tmp_path).build()
    app.shutdown()


@pytest.mark.parametrize("method", ["stop", "write_html"])
def test_a_profiler_that_fails_is_logged_and_the_build_goes_on(
    method: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Log a profiler that fails to stop or to write, and still build and shut down."""
    real = getattr(pyinstrument.Profiler, method)

    def failing(profiler: pyinstrument.Profiler, *args: Any, **kwargs: Any) -> Any:
        real(profiler, *args, **kwargs)
        raise RuntimeError("the profiler failed")

    monkeypatch.setattr(pyinstrument.Profiler, method, failing)
    app = Profiled(profile="start", profile_dir=tmp_path).build()
    app.shutdown()

    assert any(
        r.levelno == logging.ERROR and "the profiler failed" in r.getMessage()
        for r in caplog.records
    )
