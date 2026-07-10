from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pytest

from redsun.storage import SessionPathProvider


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
