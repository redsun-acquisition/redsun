"""Following the application's colour scheme, for the styles."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qtpy.QtCore import Qt as QtNamespace
from qtpy.QtGui import QGuiApplication

if TYPE_CHECKING:
    from collections.abc import Callable


class SchemeFollower:
    """Tells a style whether the colour scheme is dark, at once and at every change.

    An unknown scheme counts as light.
    """

    def __init__(self, apply: Callable[[bool], None]) -> None:
        self._apply = apply
        hints = QGuiApplication.styleHints()
        if hints is not None:
            hints.colorSchemeChanged.connect(self._tell)
        unknown = QtNamespace.ColorScheme.Unknown
        self._tell(hints.colorScheme() if hints is not None else unknown)

    def stop(self) -> None:
        """Stop telling the style about changes."""
        hints = QGuiApplication.styleHints()
        if hints is not None:
            hints.colorSchemeChanged.disconnect(self._tell)

    def _tell(self, scheme: QtNamespace.ColorScheme) -> None:
        self._apply(scheme == QtNamespace.ColorScheme.Dark)
