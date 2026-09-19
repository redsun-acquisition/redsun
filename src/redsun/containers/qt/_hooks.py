"""The hook protocols, parameterised with the Qt object each point receives."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .._hooks import (
    ConfiguresApplication,
    ConfiguresMainView,
    CreatesApplication,
    WrapsBuild,
)

if TYPE_CHECKING:
    from typing import TypeAlias

    from qtpy.QtWidgets import QApplication, QMainWindow

__all__ = [
    "QtConfiguresApplication",
    "QtConfiguresMainView",
    "QtCreatesApplication",
    "QtWrapsBuild",
]

QtCreatesApplication: TypeAlias = CreatesApplication["QApplication"]
"""Supplies the session's ``QApplication``.

Called only when no ``QApplication`` exists yet, so it sets application
identity: the class, ``argv``, attributes settable only before construction. A
theme belongs in `QtConfiguresApplication`, which runs whether or not the
application was created here. At most one hook may claim this point.
"""

QtConfiguresApplication: TypeAlias = ConfiguresApplication["QApplication"]
"""Adjusts the ``QApplication`` before any view is constructed.

The place for an application-wide style, stylesheet, font or palette.
"""

QtWrapsBuild: TypeAlias = WrapsBuild["QApplication"]
"""Wraps the build, from before the first component until the window shows.

The place for a splash screen. The returned context manager is entered before
anything is built and exited once the window is on screen, or when the build
fails; what it yields is called with each step's name.
"""

QtConfiguresMainView: TypeAlias = ConfiguresMainView["QMainWindow"]
"""Adjusts the main window after it is built and before it is shown.

Typed as ``QMainWindow``, not the container's own window class, so hooks depend
on the toolkit only.
"""
