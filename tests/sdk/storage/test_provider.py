from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pytest

from redsun.storage import BaseStorage, SessionPathProvider, StreamSpec
from redsun.storage._path_provider import PlanFilenameProvider
from redsun.storage.backends._memory import MemoryIO

if TYPE_CHECKING:
    from typing import Any

    import numpy.typing as npt


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


def frame(fill: int = 0) -> npt.NDArray[Any]:
    return np.full((4, 4), fill, dtype=np.uint16)


def test_path_provider_initialization(tmp_path: Path, path_data: PathData) -> None:
    expected_directory = tmp_path / path_data.session / path_data.date
    expected_filename = f"{path_data.plan}_00000"

    provider = SessionPathProvider(base_dir=tmp_path, session=path_data.session)
    path_info = provider()

    assert path_info.directory_path == expected_directory
    assert path_info.filename == expected_filename


def test_path_provider_setters(tmp_path: Path, path_data: PathData) -> None:
    new_path = Path.home() / "new_storage"
    new_plan = "new_plan"

    expected_directory = new_path / path_data.session / path_data.date
    expected_filename = f"{new_plan}_00000"

    provider = SessionPathProvider(base_dir=tmp_path, session=path_data.session)
    provider.set_base_dir(new_path)
    provider.set_plan(new_plan)

    path_info = provider()
    assert path_info.directory_path == expected_directory
    assert path_info.filename == expected_filename


async def test_signals_track_setters(tmp_path: Path) -> None:
    """The observable signals mirror base_dir/plan for application-level UIs."""
    provider = SessionPathProvider(base_dir=tmp_path, session="s")
    assert await provider.signals.base_dir.get_value() == str(tmp_path)
    assert await provider.signals.plan.get_value() == "unknown"

    provider.set_plan("scan")
    provider.set_base_dir(tmp_path / "elsewhere")
    assert await provider.signals.plan.get_value() == "scan"
    assert await provider.signals.base_dir.get_value() == str(tmp_path / "elsewhere")


def test_scan_existing_resumes_counters(tmp_path: Path) -> None:
    """Counters resume one past the highest number found on disk, per plan."""
    day_one = tmp_path / "s" / "2026-07-20"
    day_two = tmp_path / "s" / "2026-07-21"
    day_one.mkdir(parents=True)
    day_two.mkdir(parents=True)
    # backend-suffixed and plain filenames both parse; junk is ignored
    (day_one / "scan_00007-camera.zarr").touch()
    (day_one / "scan_00002.zarr").touch()
    (day_one / "not-a-counter.txt").touch()
    (day_two / "other_00004.h5").touch()
    # a stray file at session level must be skipped, not crash the scan
    (tmp_path / "s" / "stray.log").touch()

    provider = SessionPathProvider(base_dir=tmp_path, session="s")

    provider.set_plan("scan")
    assert provider().filename == "scan_00008"
    provider.set_plan("other")
    assert provider().filename == "other_00005"
    provider.set_plan("fresh")
    assert provider().filename == "fresh_00000"


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
    filenames.bump("scan", 41)
    assert filenames() == "scan_041"
    # bump never lowers a counter
    filenames.bump("scan", 7)
    assert filenames() == "scan_042"
    filenames.reset({})
    assert filenames() == "scan_000"


async def test_shared_provider_across_storages(tmp_path: Path) -> None:
    """Multiple storages reuse one provider: paths stay unique and monotonic."""
    provider = SessionPathProvider(base_dir=tmp_path, session="shared")
    io_a, io_b = MemoryIO(), MemoryIO()
    storage_a = BaseStorage(io=io_a, path_provider=provider)
    storage_b = BaseStorage(io=io_b, path_provider=provider)

    for storage in (storage_a, storage_b):
        storage.register(
            StreamSpec(data_key="det", shape=(4, 4), dtype="uint16", capacity=1)
        )
        sink = storage.sink("det")
        await sink.put(frame())
        await storage.close()

    assert io_a.stores[0].path.filename == "unknown_00000"
    assert io_b.stores[0].path.filename == "unknown_00001"
