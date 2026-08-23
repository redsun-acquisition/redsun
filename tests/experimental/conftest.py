from __future__ import annotations

import contextlib
import sys
from importlib.metadata import EntryPoint
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest import mock

import pytest

# mock_bundle is imported by dotted path from the manifest, so it must be
# importable the way an installed bundle would be
_TESTS_DIR = str(Path(__file__).parent)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

_MOCK_PKG_DIR = Path(__file__).parent / "mock_bundle"

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture
def config_path() -> Path:
    """Return the directory holding the test session configurations."""
    return Path(__file__).parent / "configs"


@pytest.fixture
def mock_plugin() -> Generator[None, None, None]:
    """Present ``mock_bundle`` as an installed ``redsun.plugins`` entry point.

    The loader resolves a manifest through ``entry_points`` and
    ``importlib.resources``; both are redirected at the on-disk package so
    that discovery runs for real rather than being stubbed out.
    """
    entry = mock.Mock(spec=EntryPoint)
    entry.name = "mock-bundle"
    entry.value = "redsun.yaml"
    entry.group = "redsun.plugins"

    @contextlib.contextmanager
    def as_file(path: Any) -> Generator[Path, None, None]:
        yield path if isinstance(path, Path) else Path(path)

    with (
        mock.patch("redsun.experimental._plugins.entry_points", return_value=[entry]),
        mock.patch(
            "redsun.experimental._plugins.files", side_effect=lambda _: _MOCK_PKG_DIR
        ),
        mock.patch("redsun.experimental._plugins.as_file", side_effect=as_file),
    ):
        yield
