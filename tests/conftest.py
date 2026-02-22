"""Root test configuration for redsun.

Defines the ``qt`` marker and automatically skips Qt-dependent tests
when no display is available (headless CI without ``QT_QPA_PLATFORM=offscreen``).
"""

from __future__ import annotations

import os
import sys

import pytest


def _has_display() -> bool:
    """Return True if a Qt display environment is available."""
    # offscreen platform works everywhere — check first
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        return True
    # X11 / Wayland display on Linux
    if sys.platform == "linux":
        return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
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
