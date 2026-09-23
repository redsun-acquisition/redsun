from __future__ import annotations

import contextlib
import sys
from collections.abc import Callable, Generator
from contextlib import AbstractContextManager
from importlib.metadata import EntryPoint
from importlib.util import find_spec
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from redsun.containers import AppContainer

# Add the test directory to sys.path so mock_pkg is importable
_tests_dir = str(Path(__file__).parent)
if _tests_dir not in sys.path:
    sys.path.insert(0, _tests_dir)

_MOCK_PKG_DIR = Path(__file__).parent / "mock_pkg"

# the module imports tiled, which the extra does not install on every Python
collect_ignore = [] if find_spec("tiled") else ["test_catalog.py"]


@pytest.fixture
def containers() -> Generator[list[AppContainer], None, None]:
    """Collect containers, shutting each down after the test whatever it did."""
    made: list[AppContainer] = []
    yield made
    for app in made:
        app.shutdown()


@pytest.fixture
def config_path() -> Path:
    """Return the path to test configuration files."""
    return Path(__file__).parent / "configs"


def _entry_point(name: str) -> mock.Mock:
    """Create an entry point for a plugin whose manifest is ``redsun.yaml``."""
    ep = mock.Mock(spec=EntryPoint)
    ep.name = name
    ep.value = "redsun.yaml"
    ep.group = "redsun.plugins"
    return ep


@contextlib.contextmanager
def _installed(plugins: dict[str, Path]) -> Generator[None, None, None]:
    """Patch discovery to see *plugins*, each a name and its manifest's directory.

    ``_manifest.discover`` resolves a manifest via::

        resource = files(plugin.name.replace("-", "_")) / plugin.value
        with as_file(resource) as path:
            ...

    ``files()`` returns the plugin's directory (a real ``Path``) and
    ``as_file`` is a no-op context manager yielding the path as-is.
    """
    by_package = {name.replace("-", "_"): path for name, path in plugins.items()}

    @contextlib.contextmanager
    def mock_as_file(path: Any) -> Generator[Path, None, None]:
        yield Path(path)

    with (
        mock.patch(
            "redsun._manifest.entry_points",
            return_value=[_entry_point(name) for name in plugins],
        ),
        mock.patch(
            "redsun._manifest.files",
            side_effect=by_package.__getitem__,
        ),
        mock.patch(
            "redsun._manifest.as_file",
            side_effect=mock_as_file,
        ),
    ):
        yield


@pytest.fixture
def mock_entry_points() -> Generator[None, None, None]:
    """Install the mock-pkg plugin."""
    with _installed({"mock-pkg": _MOCK_PKG_DIR}):
        yield


@pytest.fixture
def install_plugins() -> Callable[[dict[str, Path]], AbstractContextManager[None]]:
    """Return a context manager installing plugins by name and manifest directory."""
    return _installed
