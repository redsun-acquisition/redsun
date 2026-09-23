"""Root test configuration for redsun.

Defines the ``qt`` marker and automatically skips Qt-dependent tests
when no display is available (headless CI without ``QT_QPA_PLATFORM=offscreen``).
"""

from __future__ import annotations

import contextlib
import logging
import os
import sys
import time
from importlib.metadata import EntryPoint
from importlib.util import find_spec
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, TypeVar
from unittest import mock

import pytest
from psygnal._queue import QueuedCallback
from psygnal.qt import start_emitting_from_queue
from qtpy.QtWidgets import QApplication

from redsun import Session
from redsun._config import Source
from redsun.log import SERVICE_LOGGER, SessionFileHandler, logger

if TYPE_CHECKING:
    from collections.abc import Callable, Generator, Iterator, Sequence

# the module imports tiled, which the extra does not install on every Python
collect_ignore = [] if find_spec("tiled") else ["test_catalog.py"]

_TESTS_DIR = str(Path(__file__).parent)
if _TESTS_DIR not in sys.path:
    sys.path.insert(0, _TESTS_DIR)

_MOCK_PKG_DIR = Path(__file__).parent / "mock_bundle"

SessionT = TypeVar("SessionT", bound=Session)


@pytest.fixture
def wait_until() -> Callable[..., bool]:
    """Return a poll that holds until ``predicate`` is true or ``timeout`` runs out.

    For a thread or a process that offers nothing to wait on. Where an event,
    a future or a task exists, wait on that instead.
    """

    def poll(predicate: Callable[[], bool], timeout: float = 10.0) -> bool:
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            if predicate():
                return True
            time.sleep(0.005)
        return predicate()

    return poll


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication([])

    start_emitting_from_queue()
    return app


@pytest.fixture
def launchable(monkeypatch: pytest.MonkeyPatch) -> None:
    """Let a launched service import ``mock_pkg``, and restore the CA address list.

    The transport's port map is left alone: libca reads the address list once per
    process, so a service keeps the port it first got from test to test.
    """
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).parent / "launchable"))
    monkeypatch.setenv("EPICS_CA_ADDR_LIST", "")


@pytest.fixture(autouse=True)
def log_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Write session log files under *tmp_path*, and close any a test left open.

    A container opens a log file when it is constructed; without this, every
    test building one would write to the user's own log directory.
    """
    monkeypatch.setattr("redsun.log.user_data_dir", lambda *a, **k: str(tmp_path))
    yield tmp_path / "logs"
    loggers = [
        logging.getLogger(name)
        for name in list(logging.Logger.manager.loggerDict)
        if name.startswith(SERVICE_LOGGER)
    ]
    for owner in (logger, *loggers):
        for handler in [h for h in owner.handlers if isinstance(h, SessionFileHandler)]:
            owner.removeHandler(handler)
            handler.close()


@pytest.fixture(autouse=True)
def data_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Put the default root of acquisition files and catalogs under *tmp_path*.

    Without this, every test building a session with a catalog would start
    one in the user's own data directory.
    """
    root = tmp_path / "data"
    monkeypatch.setattr("redsun.path_provider.user_data_dir", lambda *a, **k: str(root))
    return root


@pytest.fixture(autouse=True)
def empty_emission_queue() -> Iterator[None]:
    """Drop every psygnal emission a test left queued for a thread.

    A slot with a thread affinity receives an emission from another thread
    through a queue that only the event loop drains. Left there, it is
    delivered by the next test that runs the loop, to whatever its target has
    become, and a destroyed widget ends the interpreter.
    """
    yield
    # psygnal offers no public way to drop queued emissions
    for queue in QueuedCallback._GLOBAL_QUEUE.values():
        while not queue.empty():
            queue.get_nowait()


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


class BuildSession(Protocol):
    """Build a session, and hand it back typed as what was asked for."""

    def __call__(
        self,
        container: type[SessionT] | SessionT,
        config: Source | Sequence[Source] | None = ...,
        /,
    ) -> SessionT: ...


@pytest.fixture
def config_path() -> Path:
    """Return the directory holding the test session configurations."""
    return Path(__file__).parent / "configs"


@pytest.fixture
def build() -> Generator[BuildSession, None, None]:
    """Return a function building a session and shutting it down afterwards.

    Parameters
    ----------
    container : type[SessionT] | SessionT
        A container class, or a container already in hand.
    config : Source | None
        Laid over what the class declares, for a container built here.

    Every session it built is shut down in reverse order once the test ends,
    and a test may shut one down itself, ``shutdown`` running nothing the
    second time.
    """
    built: list[Session] = []

    def build_one(
        container: type[SessionT] | SessionT,
        config: Source | Sequence[Source] | None = None,
        /,
    ) -> SessionT:
        unbuilt = container(config) if isinstance(container, type) else container
        session = unbuilt.build()
        built.append(session)
        return session

    yield build_one
    for session in reversed(built):
        session.shutdown()


@pytest.fixture
def config_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point the settings store at *tmp_path*, off the user's own directory."""
    monkeypatch.setattr(
        "redsun._settings.user_config_dir", lambda *a, **k: str(tmp_path)
    )
    return tmp_path


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
    def as_file(path: str | Path) -> Generator[Path, None, None]:
        yield path if isinstance(path, Path) else Path(path)

    with (
        mock.patch("redsun.session._plugins.entry_points", return_value=[entry]),
        mock.patch(
            "redsun.session._plugins.files",
            side_effect=lambda _: _MOCK_PKG_DIR,
        ),
        mock.patch("redsun.session._plugins.as_file", side_effect=as_file),
    ):
        yield
