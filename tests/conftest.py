from __future__ import annotations

import contextlib
import sys
from pathlib import Path
from typing import Any, Generator
from unittest import mock

import pytest
from importlib.metadata import EntryPoint

# Add the test directory to sys.path so mock_pkg is importable
_tests_dir = str(Path(__file__).parent)
if _tests_dir not in sys.path:
    sys.path.insert(0, _tests_dir)

_MOCK_PKG_DIR = Path(__file__).parent / "mock_pkg"


@pytest.fixture
def config_path() -> Path:
    """Return the path to test configuration files."""
    return Path(__file__).parent / "configs"


def _make_mock_entry_point() -> mock.Mock:
    """Create a mock entry point for the mock-pkg plugin."""
    ep = mock.Mock(spec=EntryPoint)
    ep.name = "mock-pkg"
    ep.value = "redsun.yaml"
    ep.group = "redsun.plugins"
    return ep


@pytest.fixture
def mock_entry_points() -> Generator[Any, None, None]:
    """Patch entry_points and importlib.resources to use mock-pkg manifest.

    ``plugins.py`` resolves the manifest via::

        pkg_manifest = files(plugin.name.replace("-", "_")) / plugin.value
        with as_file(pkg_manifest) as manifest_path: ...

    We mock ``files()`` to return the mock_pkg directory (a real ``Path``)
    and ``as_file`` to be a no-op context manager yielding the path as-is.
    """
    ep = _make_mock_entry_point()

    def mock_files(package: str) -> Path:
        return _MOCK_PKG_DIR

    @contextlib.contextmanager
    def mock_as_file(path: Any) -> Generator[Path, None, None]:
        yield Path(path) if not isinstance(path, Path) else path

    with (
        mock.patch(
            "redsun.plugins.entry_points",
            return_value=[ep],
        ),
        mock.patch(
            "redsun.plugins.files",
            side_effect=mock_files,
        ),
        mock.patch(
            "redsun.plugins.as_file",
            side_effect=mock_as_file,
        ),
    ):
        yield
