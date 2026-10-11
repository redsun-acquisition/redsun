"""napari's look for a Qt session, following its colour scheme."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from platformdirs import user_cache_dir
from qtpy.QtCore import Qt as QtNamespace
from qtpy.QtGui import QGuiApplication

from ._vendor._napari.icons import write_icons
from ._vendor._napari.theme import DARK, LIGHT, stylesheet

if TYPE_CHECKING:
    from qtpy.QtWidgets import QApplication

__all__ = ["NapariStyle"]


class NapariStyle:
    """Gives the window napari's look, dark or light as the colour scheme reads.

    A `configure_application` hook provider. It applies napari's stylesheet
    and icons for the current colour scheme, then again at every change of
    the scheme, so the session's colour scheme control switches between
    napari's dark and light themes. An unknown scheme gets the light theme.
    Both themes' icons are written to the user's cache folder when the
    session builds. At shutdown the application gets back the stylesheet it
    had before.

    Parameters
    ----------
    font_size
        The stylesheet's base font size in points; `None` keeps napari's own
        size for the platform.

    Raises
    ------
    ValueError
        If *font_size* is not a positive whole number.
    """

    def __init__(self, font_size: int | None = None) -> None:
        if font_size is not None and (
            isinstance(font_size, bool)
            or not isinstance(font_size, int)
            or font_size < 1
        ):
            raise ValueError(
                "font_size must be a positive whole number of points, "
                f"got {font_size!r}"
            )
        self._font_size = font_size
        self._app: QApplication | None = None
        self._previous = ""
        self._sheets: dict[str, str] = {}

    def configure_application(self, app: QApplication) -> None:
        """Apply napari's theme for the current colour scheme, and again on each change."""
        self._app = app
        self._previous = app.styleSheet()
        # files are written here, where a failure stops the build, rather than
        # in the slot a scheme change calls
        cache = Path(user_cache_dir("redsun", appauthor=False)) / "napari-style"
        sized = {} if self._font_size is None else {"font_size": f"{self._font_size}pt"}
        self._sheets = {
            theme.name: stylesheet(
                replace(theme, **sized), write_icons(theme, cache / theme.name)
            )
            for theme in (DARK, LIGHT)
        }
        hints = QGuiApplication.styleHints()
        if hints is not None:
            hints.colorSchemeChanged.connect(self._apply)
        unknown = QtNamespace.ColorScheme.Unknown
        self._apply(hints.colorScheme() if hints is not None else unknown)

    def shutdown(self) -> None:
        """Stop following the colour scheme, and restore the previous stylesheet."""
        if self._app is None:
            return
        hints = QGuiApplication.styleHints()
        if hints is not None:
            hints.colorSchemeChanged.disconnect(self._apply)
        self._app.setStyleSheet(self._previous)
        self._app = None

    def _apply(self, scheme: QtNamespace.ColorScheme) -> None:
        theme = DARK if scheme == QtNamespace.ColorScheme.Dark else LIGHT
        if self._app is not None:
            self._app.setStyleSheet(self._sheets[theme.name])
