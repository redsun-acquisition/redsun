"""A session writes each run's records to a rotated file in the user's log directory."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

import pytest
import yaml

from redsun import Session, log
from redsun.log import SessionFileHandler, add_handler, remove_handler, session_log

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

RUN_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}_\d+\.log$")


class Empty(Session):
    pass


@pytest.fixture
def redsun_logger() -> Iterator[logging.Logger]:
    """Yield the ``redsun`` logger at ``DEBUG``, restoring its level afterwards."""
    logger = logging.getLogger("redsun")
    level = logger.level
    logger.setLevel(logging.DEBUG)
    yield logger
    logger.setLevel(level)


def open_handler(session: str) -> SessionFileHandler:
    handler = SessionFileHandler(session)
    add_handler(handler)
    return handler


def close_handler(handler: SessionFileHandler) -> None:
    remove_handler(handler)
    handler.close()


def test_a_run_is_written_to_a_file_in_the_session_folder(
    log_directory: Path, redsun_logger: logging.Logger
) -> None:
    """The folder is the session's name made safe for a path."""
    handler = open_handler("my lab: day 1")
    redsun_logger.warning("stage homed")
    close_handler(handler)

    (run,) = (log_directory / "my_lab_day_1" / "app").iterdir()
    assert RUN_NAME.match(run.name)
    assert "stage homed" in run.read_text(encoding="utf-8")


@pytest.mark.parametrize(("session", "folder"), [("..", "_"), (".hidden", "hidden")])
def test_a_session_name_cannot_climb_out_of_the_log_directory(
    log_directory: Path, session: str, folder: str
) -> None:
    handler = open_handler(session)
    close_handler(handler)

    assert (log_directory / folder / "app").is_dir()


def test_a_rotated_run_lists_its_files_oldest_first(
    log_directory: Path,
    redsun_logger: logging.Logger,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(log, "LOG_MAX_BYTES", 300)
    monkeypatch.setattr(log, "LOG_BACKUPS", 2)
    handler = open_handler("rotation")

    for i in range(40):
        redsun_logger.info("record %03d", i)
    handler.flush()

    files = handler.files
    text = "".join(path.read_text(encoding="utf-8") for path in files)
    numbers = [int(n) for n in re.findall(r"record (\d{3})", text)]
    close_handler(handler)

    assert len(files) == 3
    assert numbers == sorted(numbers)
    assert numbers[-1] == 39


def test_opening_a_run_deletes_all_but_the_most_recent_runs(
    log_directory: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(log, "LOG_RUNS_KEPT", 3)
    app_folder = log_directory / "pruned" / "app"
    services_folder = log_directory / "pruned" / "services"
    app_folder.mkdir(parents=True)
    services_folder.mkdir(parents=True)
    for day in range(1, 6):
        run = f"2026-09-0{day}T10-00-00_1"
        for name in (".log", ".log.1"):
            (app_folder / f"{run}{name}").write_text("run")
        for name in (".cam.log", ".cam.log.1"):
            (services_folder / f"{run}{name}").write_text("run")

    handler = open_handler("pruned")
    close_handler(handler)

    kept = sorted(path.name for path in app_folder.iterdir())
    assert kept[:4] == [
        f"2026-09-0{day}T10-00-00_1{name}"
        for day in (4, 5)
        for name in (".log", ".log.1")
    ]
    assert len(kept) == 5
    assert sorted(path.name for path in services_folder.iterdir()) == [
        f"2026-09-0{day}T10-00-00_1{name}"
        for day in (4, 5)
        for name in (".cam.log", ".cam.log.1")
    ]


def test_a_service_writes_a_file_of_its_own_under_services(
    log_directory: Path, redsun_logger: logging.Logger
) -> None:
    """The application's file takes no service record; a silent service has no file."""
    application = open_handler("lab")
    camera = SessionFileHandler("lab", "cam", application.run)
    silent = SessionFileHandler("lab", "stage", application.run)
    add_handler(camera, "cam")
    add_handler(silent, "stage")

    redsun_logger.warning("stage homed")
    logging.getLogger("redsun.service.cam.caproto").warning("frame dropped")
    close_handler(application)
    for name, handler in (("cam", camera), ("stage", silent)):
        remove_handler(handler, name)
        handler.close()

    files = {
        path.name: path.read_text(encoding="utf-8")
        for folder in ("app", "services")
        for path in (log_directory / "lab" / folder).iterdir()
    }
    assert set(files) == {f"{application.run}.log", f"{application.run}.cam.log"}
    assert (log_directory / "lab" / "app" / f"{application.run}.log").is_file()
    assert (log_directory / "lab" / "services" / f"{application.run}.cam.log").is_file()
    assert "stage homed" in files[f"{application.run}.log"]
    assert "frame dropped" not in files[f"{application.run}.log"]
    assert "frame dropped" in files[f"{application.run}.cam.log"]


@pytest.mark.skip(reason="the session does not open its log yet")
def test_a_session_opens_the_log_and_shutdown_closes_it(log_directory: Path) -> None:
    """Open from construction, closed by shutdown whether or not it was built."""
    app = Empty({"session": "lab"})
    handler = session_log()
    assert handler is not None
    assert (log_directory / "lab" / "app").is_dir()

    app.shutdown()
    assert session_log() is None

    app.build()
    assert session_log() is not None
    app.shutdown()
    assert session_log() is None


def test_a_run_moves_with_the_root(
    tmp_path: Path, redsun_logger: logging.Logger
) -> None:
    """Records before and after the move end in one file under the new root."""
    application = SessionFileHandler("lab", root=tmp_path / "a")
    camera = SessionFileHandler("lab", "cam", application.run, root=tmp_path / "a")
    silent = SessionFileHandler("lab", "stage", application.run, root=tmp_path / "a")
    add_handler(application)
    add_handler(camera, "cam")
    add_handler(silent, "stage")
    redsun_logger.warning("before the move")
    logging.getLogger("redsun.service.cam").warning("cam before")

    for handler in (application, camera, silent):
        handler.move(tmp_path / "b")
    redsun_logger.warning("after the move")
    logging.getLogger("redsun.service.stage").warning("stage after")

    close_handler(application)
    for name, handler in (("cam", camera), ("stage", silent)):
        remove_handler(handler, name)
        handler.close()

    assert application.root == tmp_path / "b"
    assert not any((tmp_path / "a" / "logs" / "lab").rglob("*.log*"))
    (app_file,) = (tmp_path / "b" / "logs" / "lab" / "app").iterdir()
    assert app_file.name == f"{application.run}.log"
    lines = app_file.read_text("utf-8").splitlines()
    assert len(lines) == 2
    assert "before the move" in lines[0]
    assert "after the move" in lines[1]
    services = {
        path.name: path.read_text("utf-8")
        for path in (tmp_path / "b" / "logs" / "lab" / "services").iterdir()
    }
    assert set(services) == {
        f"{application.run}.cam.log",
        f"{application.run}.stage.log",
    }
    assert "cam before" in services[f"{application.run}.cam.log"]
    assert "stage after" in services[f"{application.run}.stage.log"]


@pytest.mark.skip(reason="the session does not open its log yet")
def test_a_session_moves_the_log_when_the_root_changes(
    log_directory: Path, tmp_path: Path
) -> None:
    """The log follows storage.base_dir at build and set_base_dir afterwards."""
    cfg_file = tmp_path / "session.yaml"
    cfg_file.write_text(
        yaml.dump(
            {
                "schema_version": 1.0,
                "session": "lab",
                "storage": {"base_dir": str(tmp_path / "root")},
            }
        )
    )
    app = Session.from_config(str(cfg_file))
    handler = session_log()
    assert handler is not None
    assert handler.root == log_directory.parent

    app.build()
    assert (tmp_path / "root" / "logs" / "lab" / "app" / f"{handler.run}.log").is_file()

    app.path_provider.set_base_dir(tmp_path / "other")
    app.shutdown()

    assert not (
        tmp_path / "root" / "logs" / "lab" / "app" / f"{handler.run}.log"
    ).exists()
    assert (
        tmp_path / "other" / "logs" / "lab" / "app" / f"{handler.run}.log"
    ).is_file()
