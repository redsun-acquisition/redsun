"""The hook protocols named for the objects Qt gives each moment."""

from __future__ import annotations

from typing import TYPE_CHECKING

from redsun.containers._hooks import (
    ConfiguresApplication,
    ConfiguresMainView,
    CreatesApplication,
)

if TYPE_CHECKING:
    from typing import TypeAlias

    from qtpy.QtWidgets import QApplication, QMainWindow

__all__ = [
    "QtConfiguresApplication",
    "QtConfiguresMainView",
    "QtCreatesApplication",
]

QtCreatesApplication: TypeAlias = CreatesApplication["QApplication"]
"""Supplies the ``QApplication`` the session runs on."""

QtConfiguresApplication: TypeAlias = ConfiguresApplication["QApplication"]
"""Adjusts the ``QApplication`` before any view is constructed.

Where an application-wide style, stylesheet, font or palette belongs: the
build phase that follows constructs every view.
"""

QtConfiguresMainView: TypeAlias = ConfiguresMainView["QMainWindow"]
"""Adjusts the main window after it is built and before it is shown.

Bound to ``QMainWindow`` rather than to the concrete window the container
builds, so that a hook is written against the toolkit and the window class
stays free to change.
"""
