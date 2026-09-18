from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytest

from redsun.path_provider import (
    PlanFilenameProvider,
    SessionPathProvider,
    session_directory,
)


@dataclass
class PathData:
    plan: str
    session: str
    date: str


@pytest.fixture(scope="module")
def path_data() -> PathData:
    return PathData(
        plan="unknown", session="test_session", date=datetime.now().strftime("%Y-%m-%d")
    )


def test_default_base_dir_is_the_user_data_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Files land under the same root as the logs, not under ``~``."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    provider = SessionPathProvider(session="s")

    assert provider().directory_path.parent == session_directory("s")


def test_the_old_location_is_named_when_it_still_exists(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Nothing is moved, so whoever goes looking is told where the files went."""
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / "redsun-storage").mkdir()

    with caplog.at_level("WARNING", logger="redsun"):
        SessionPathProvider(base_dir=tmp_path / "new", session="s")

    assert "redsun-storage" in caplog.text


def test_path_provider_initialization(tmp_path: Path, path_data: PathData) -> None:
    expected_directory = tmp_path / path_data.session / path_data.date
    expected_filename = f"{path_data.plan}_00000"

    provider = SessionPathProvider(base_dir=tmp_path, session=path_data.session)
    path_info = provider()

    assert path_info.directory_path == expected_directory
    assert path_info.filename == expected_filename


def test_path_provider_setters(tmp_path: Path, path_data: PathData) -> None:
    new_path = tmp_path / "new_storage"
    new_plan = "new_plan"

    expected_directory = new_path / path_data.session / path_data.date
    expected_filename = f"{new_plan}_00000"

    provider = SessionPathProvider(base_dir=tmp_path, session=path_data.session)
    provider.set_base_dir(new_path)
    provider.set_plan(new_plan)

    path_info = provider()
    assert path_info.directory_path == expected_directory
    assert path_info.filename == expected_filename

    provider.reset_plan()
    assert provider().filename == "unknown_00000"


def test_each_data_key_gets_its_own_directory_and_counter(tmp_path: Path) -> None:
    """Two detectors in one run write the same name in directories of their own."""
    provider = SessionPathProvider(base_dir=tmp_path, session="s")
    provider.set_plan("scan")

    first, second = provider("det_a"), provider("det_b")

    assert first.filename == second.filename == "scan_00000"
    assert first.directory_path.name == "det_a"
    assert second.directory_path.name == "det_b"
    assert first.directory_path.parent == second.directory_path.parent
    # the same key twice still never repeats a name
    assert provider("det_a").filename == "scan_00001"


def test_scan_existing_resumes_counters(tmp_path: Path) -> None:
    """Counters resume one past the highest number on disk, per plan and key."""
    day_one = tmp_path / "s" / "2026-07-20"
    day_two = tmp_path / "s" / "2026-07-21"
    (day_one / "det").mkdir(parents=True)
    day_two.mkdir(parents=True)
    # a Zarr store is a directory, and counts like a file
    (day_one / "det" / "scan_00007.zarr").mkdir()
    (day_one / "det" / "scan_00002.zarr").touch()
    (day_one / "det" / "not-a-counter.txt").touch()
    # written before per-key directories, so it counts for no key
    (day_two / "other_00004.h5").touch()
    # a stray file at session level must be skipped, not crash the scan
    (tmp_path / "s" / "stray.log").touch()

    provider = SessionPathProvider(base_dir=tmp_path, session="s")

    provider.set_plan("scan")
    assert provider("det").filename == "scan_00008"
    # a key with nothing on disk starts from zero, whatever its siblings did
    assert provider("fresh_det").filename == "scan_00000"
    provider.set_plan("other")
    assert provider().filename == "other_00005"


@pytest.mark.parametrize(
    "stored", ["scan_00004", "scan_00004.zarr", "scan_00004.ome.zarr"]
)
def test_a_store_with_several_suffixes_counts(tmp_path: Path, stored: str) -> None:
    """``scan_00004.ome.zarr`` is number 4, so the next file is not a repeat."""
    (tmp_path / "s" / "2026-07-20" / "det" / stored).mkdir(parents=True)

    provider = SessionPathProvider(base_dir=tmp_path, session="s")
    provider.set_plan("scan")

    assert provider("det").filename == "scan_00005"


def test_a_locked_root_cannot_move(tmp_path: Path) -> None:
    provider = SessionPathProvider(base_dir=tmp_path, session="s")
    provider.lock_base_dir("a catalog reads from it")

    with pytest.raises(RuntimeError, match="a catalog reads from it"):
        provider.set_base_dir(tmp_path / "elsewhere")

    assert provider.base_dir == tmp_path


def test_the_root_cannot_move_while_a_plan_runs(tmp_path: Path) -> None:
    """A run's remaining files must not land somewhere else than its first ones."""
    provider = SessionPathProvider(base_dir=tmp_path, session="s")
    provider.set_plan("scan")

    with pytest.raises(RuntimeError, match="is running"):
        provider.set_base_dir(tmp_path / "elsewhere")

    assert provider.base_dir == tmp_path

    provider.reset_plan()
    provider.set_base_dir(tmp_path / "elsewhere")

    assert provider.base_dir == tmp_path / "elsewhere"


def test_set_base_dir_rescans_new_location(tmp_path: Path) -> None:
    """Changing base_dir resets counters and adopts the new location's state."""
    base_a = tmp_path / "a"
    base_b = tmp_path / "b"
    (base_b / "s" / "2026-07-20").mkdir(parents=True)
    (base_b / "s" / "2026-07-20" / "unknown_00009.h5").touch()

    provider = SessionPathProvider(base_dir=base_a, session="s")
    assert provider().filename == "unknown_00000"

    provider.set_base_dir(base_b)
    assert provider().filename == "unknown_00010"


def test_counter_continues_across_dates(tmp_path: Path) -> None:
    """The date directory groups files; it does not scope the counter."""
    clock = {"now": datetime(2026, 7, 20, 12, 0, 0)}
    provider = SessionPathProvider(
        base_dir=tmp_path, session="s", now=lambda: clock["now"]
    )

    first = provider()
    clock["now"] = datetime(2026, 7, 21, 0, 30, 0)
    second = provider()

    assert first.directory_path.name == "2026-07-20"
    assert second.directory_path.name == "2026-07-21"
    assert first.filename == "unknown_00000"
    assert second.filename == "unknown_00001"


def test_filename_provider_accessors_and_padding() -> None:
    """PlanFilenameProvider exposes plan/max_digits and honors the padding."""
    filenames = PlanFilenameProvider(max_digits=3)
    assert filenames.plan == "unknown"
    assert filenames.max_digits == 3
    assert filenames() == "unknown_000"
    filenames.set_plan("scan")
    filenames.bump("scan", "det", 41)
    assert filenames("det") == "scan_041"
    # bump never lowers a counter
    filenames.bump("scan", "det", 7)
    assert filenames("det") == "scan_042"
    # another data key counts on its own
    assert filenames("other") == "scan_000"
    filenames.reset({})
    assert filenames("det") == "scan_000"
