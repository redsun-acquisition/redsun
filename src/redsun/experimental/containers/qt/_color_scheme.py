"""The colour-scheme control a Qt session pins to its toolbar."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Any, ClassVar, Self

from qtpy.QtCore import Qt as QtNamespace
from qtpy.QtGui import QGuiApplication
from qtpy.QtWidgets import QSizePolicy, QToolButton, QWidget

if TYPE_CHECKING:
    from collections.abc import Mapping

    from qtpy.QtWidgets import QMainWindow

__all__ = ["ColorSchemeButton", "ColorSchemeMode"]

CONFIG_KEY = "color_scheme"
"""The configuration key naming the mode a session starts in."""


class ColorSchemeMode(StrEnum):
    """What a session asks the platform for, in the order the control cycles.

    ``SYSTEM`` asks for nothing, which is Qt's unset state rather than a
    scheme of its own: the platform keeps deciding, and a user changing their
    own setting is followed.
    """

    SYSTEM = "system"
    LIGHT = "light"
    DARK = "dark"

    @classmethod
    def from_config(cls, config: Mapping[str, Any]) -> Self:
        """Return the mode *config* names, or `SYSTEM` when it names none.

        Raises
        ------
        ValueError
            If the key names no mode the control offers.
        """
        declared = config.get(CONFIG_KEY)
        return cls(declared) if declared is not None else cls(cls.SYSTEM)

    @property
    def glyph(self) -> str:
        """The character the control shows while this mode is asked for."""
        return _GLYPHS[self]

    def apply(self) -> None:
        """Ask the platform for this scheme, or stop asking under `SYSTEM`.

        Raises
        ------
        RuntimeError
            If no application exists yet to carry a colour scheme.
        """
        hints = QGuiApplication.styleHints()
        if hints is None:
            raise RuntimeError(
                "a colour scheme belongs to an application, and none is running"
            )
        if self is ColorSchemeMode.SYSTEM:
            hints.unsetColorScheme()
        else:
            hints.setColorScheme(_SCHEMES[self])

    def next(self) -> ColorSchemeMode:
        """Return the mode after this one, wrapping past the last."""
        order = list(ColorSchemeMode)
        return order[(order.index(self) + 1) % len(order)]


_SCHEMES: dict[ColorSchemeMode, QtNamespace.ColorScheme] = {
    ColorSchemeMode.LIGHT: QtNamespace.ColorScheme.Light,
    ColorSchemeMode.DARK: QtNamespace.ColorScheme.Dark,
}

_GLYPHS: dict[ColorSchemeMode, str] = {
    ColorSchemeMode.SYSTEM: "\u25d0",
    ColorSchemeMode.LIGHT: "\u2600",
    ColorSchemeMode.DARK: "\u263e",
}


class ColorSchemeButton(QToolButton):
    """Cycles the colour scheme, system to light to dark and back.

    The glyph is the mode asked for rather than the scheme in force, so it
    stays right while ``system`` follows a user changing their own setting.
    """

    TOOLBAR: ClassVar[str] = "redsun.color-scheme"
    """Object name of the toolbar `pin_to` puts the control in."""

    def __init__(
        self,
        mode: ColorSchemeMode = ColorSchemeMode.SYSTEM,
        parent: QWidget | None = None,
    ) -> None:
        """Show *mode*, without applying it: the session already did."""
        super().__init__(parent)
        self._mode = mode
        self.setAutoRaise(True)
        self.setToolButtonStyle(QtNamespace.ToolButtonStyle.ToolButtonTextOnly)
        self.setCursor(QtNamespace.CursorShape.PointingHandCursor)
        font = self.font()
        font.setPointSize(font.pointSize() + 3)
        self.setFont(font)
        self.clicked.connect(self.cycle)
        self._show_mode()

    @classmethod
    def pin_to(cls, window: QMainWindow, mode: ColorSchemeMode) -> Self:
        """Return a control at the right of a toolbar of its own on *window*.

        An expanding spacer takes the width before it, which is what pins the
        control to the right edge; nothing else goes in this toolbar, so a
        view asking for a toolbar keeps its own.

        Raises
        ------
        RuntimeError
            If *window* refuses a toolbar.
        """
        bar = window.addToolBar(cls.TOOLBAR)
        if bar is None:
            raise RuntimeError(f"{type(window).__name__} refused a toolbar")
        bar.setObjectName(cls.TOOLBAR)
        bar.setMovable(False)
        spacer = QWidget(bar)
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        bar.addWidget(spacer)
        control = cls(mode, bar)
        bar.addWidget(control)
        return control

    @property
    def mode(self) -> ColorSchemeMode:
        """The mode asked for, which the glyph shows."""
        return self._mode

    def cycle(self) -> None:
        """Move to the next mode and ask the platform for it."""
        self._mode = self._mode.next()
        self._mode.apply()
        self._show_mode()

    def _show_mode(self) -> None:
        self.setText(self._mode.glyph)
        self.setToolTip(f"Colour scheme: {self._mode} (click to change)")
