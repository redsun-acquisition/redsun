"""Root test configuration for redsun.

Defines the ``qt`` marker and automatically skips Qt-dependent tests
when no display is available (headless CI without ``QT_QPA_PLATFORM=offscreen``).
"""

from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

import pytest
from psygnal._queue import QueuedCallback
from psygnal.qt import start_emitting_from_queue
from qtpy.QtWidgets import QApplication

from redsun.log import SessionFileHandler, logger

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    app = QApplication([])

    start_emitting_from_queue()
    return app


@pytest.fixture(autouse=True)
def log_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Write session log files under *tmp_path*, and close any a test left open.

    A container opens a log file when it is constructed; without this, every
    test building one would write to the user's own log directory.
    """
    monkeypatch.setattr("redsun.log.user_log_dir", lambda *a, **k: str(tmp_path))
    yield tmp_path
    for handler in [h for h in logger.handlers if isinstance(h, SessionFileHandler)]:
        logger.removeHandler(handler)
        handler.close()


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


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Auto-skip @pytest.mark.qt tests in headless environments."""
    if _has_display():
        return
    for item in items:
        if item.get_closest_marker("qt"):
            item.add_marker(_SKIP_QT)
