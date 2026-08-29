"""The hook protocols named for the objects Qt gives each moment."""

from __future__ import annotations

from typing import TYPE_CHECKING

from redsun.containers._hooks import (
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
"""Supplies the ``QApplication`` the session runs on.

Consulted only when no ``QApplication`` is running yet, so it is the place for
application identity - the class, ``argv``, the attributes that can only be set
before construction - and never the place for a theme, which
`QtConfiguresApplication` delivers whether or not the application was created
here. At most one hook may claim it.
"""

QtConfiguresApplication: TypeAlias = ConfiguresApplication["QApplication"]
"""Adjusts the ``QApplication`` before any view is constructed.

Where an application-wide style, stylesheet, font or palette belongs: the
build phase that follows constructs every view.
"""

QtWrapsBuild: TypeAlias = WrapsBuild["QApplication"]
"""Wraps the whole build, from before the first component until the window shows.

Where a splash screen belongs: the context manager it returns is entered before
anything is built and exited once the window is on screen, and what it yields is
called with the name of each step. Exited on a failed build too, so nothing is
left covering an application that never got a window.
"""

QtConfiguresMainView: TypeAlias = ConfiguresMainView["QMainWindow"]
"""Adjusts the main window after it is built and before it is shown.

Bound to ``QMainWindow`` rather than to the concrete window the container
builds, so that a hook is written against the toolkit and the window class
stays free to change.
"""
