"""Root test configuration for redsun.

Defines the `qt` marker and automatically skips Qt-dependent tests
when no display is available (headless CI without `QT_QPA_PLATFORM=offscreen`).
"""

from __future__ import annotations

import contextlib
import os
import sys
import time
from importlib.metadata import EntryPoint
from importlib.util import find_spec
from pathlib import Path
from typing import TYPE_CHECKING
from unittest import mock

import pytest
from psygnal.qt import start_emitting_from_queue
from qtpy.QtCore import QCoreApplication
from qtpy.QtGui import QGuiApplication
from qtpy.QtWidgets import QApplication

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

# the module imports tiled, which the extra does not install on every Python
collect_ignore = [] if find_spec("tiled") else ["test_catalog.py"]

_TESTS_DIR = str(Path(__file__).parent)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

_MOCK_PKG_DIR = Path(__file__).parent / "mock_bundle"


@pytest.fixture
def wait_until() -> Callable[..., bool]:
    """Return a poll that holds until `predicate` is true or `timeout` runs out.

    Qt events are processed between checks, so a signal queued to the main
    thread is delivered while the poll waits. For a thread or a process that
    offers nothing to wait on. Where an event, a future or a task exists, wait
    on that instead.
    """

    def poll(predicate: Callable[[], bool], timeout: float = 10.0) -> bool:
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            if predicate():
                return True
            QCoreApplication.processEvents()
            time.sleep(0.005)
        return predicate()

    return poll


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    """Return the one `QApplication` of the whole run."""
    app = QApplication([])

    start_emitting_from_queue()
    return app


@pytest.fixture
def unstyled(
    qapp: QApplication, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Generator[None, None, None]:
    """Write a style's files under `tmp_path`, and leave the application unstyled."""
    monkeypatch.setattr(
        "redsun.qt.styles.napari.user_cache_dir", lambda *a, **k: str(tmp_path)
    )
    yield
    hints = QGuiApplication.styleHints()
    assert hints is not None
    # a test that failed before the style connected leaves nothing to disconnect
    with contextlib.suppress(TypeError, RuntimeError):
        hints.colorSchemeChanged.disconnect()
    qapp.setStyleSheet("")


@pytest.fixture
def launchable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Let a launched service import `mock_pkg`, and restore the CA address list.

    The transport's port map is left alone: libca reads the address list once per
    process, so a service keeps the port it first got from test to test.
    """
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).parent / "launchable"))
    monkeypatch.setenv("EPICS_CA_ADDR_LIST", "")


def _has_display() -> bool:
    """Return True if a Qt display environment is available."""
    # offscreen platform works everywhere - check first
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        return True
    # X11 / Wayland display on Linux
    if sys.platform == "linux":
        return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
    else:
        # macOS and Windows always have a display in normal environments
        return True


_SKIP_QT = pytest.mark.skip(
    reason="requires a Qt display; set QT_QPA_PLATFORM=offscreen or run with pytest-env"
)

_SKIP_COMPOSE = pytest.mark.skip(
    reason="requires tests/compose/compose.yaml up and REDSUN_COMPOSE set"
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Auto-skip Qt tests in headless environments, and compose tests unless asked for."""
    display = _has_display()
    compose = bool(os.environ.get("REDSUN_COMPOSE"))
    for item in items:
        if not display and item.get_closest_marker("qt"):
            item.add_marker(_SKIP_QT)
        if not compose and item.get_closest_marker("compose"):
            item.add_marker(_SKIP_COMPOSE)


@pytest.fixture
def config_path() -> Path:
    """Return the directory holding the test session configurations."""
    return Path(__file__).parent / "configs"


@pytest.fixture
def mock_plugin() -> Generator[None, None, None]:
    """Present `mock_bundle` as an installed `redsun.plugins` entry point.

    The loader resolves a manifest through `entry_points` and
    `importlib.resources`; both are redirected at the on-disk package so
    that discovery runs for real rather than being stubbed out.
    """
    entry = mock.Mock(spec=EntryPoint)
    entry.name = "mock-bundle"
    entry.value = "redsun.yaml"
    entry.group = "redsun.plugins"

    @contextlib.contextmanager
    def as_file(path: str | Path) -> Generator[Path, None, None]:
        yield path if isinstance(path, Path) else Path(path)

    with (
        mock.patch("redsun._manifest.entry_points", return_value=[entry]),
        mock.patch(
            "redsun._manifest.files",
            side_effect=lambda _: _MOCK_PKG_DIR,
        ),
        mock.patch("redsun._manifest.as_file", side_effect=as_file),
    ):
        yield
