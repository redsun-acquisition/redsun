"""`qlementine`'s look for a Qt session, following its colour scheme."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any, NamedTuple

from qtpy import API
from qtpy.QtCore import Qt as QtNamespace
from qtpy.QtGui import QPalette
from qtpy.QtWidgets import QStyle

from ._scheme import SchemeFollower

if TYPE_CHECKING:
    from types import ModuleType

    from qtpy.QtGui import QFont
    from qtpy.QtWidgets import QApplication

__all__ = ["QlementineStyle"]

MODULES = {"pyqt6": "PyQt6Qlementine", "pyside6": "PySide6Qlementine"}
"""The package holding `qlementine` for each Qt binding."""

EXTRAS = {"pyqt6": "qlementine-pyqt", "pyside6": "qlementine-pyside"}
"""The extra of `redsun` that installs the package, for each Qt binding."""


class Earlier(NamedTuple):
    """How the application looked before the style."""

    style: str
    """The name of its style; empty for a style that has none."""

    font: QFont
    """Its font."""

    palette: QPalette
    """Its palette if one had been set on it, or else an empty one, which asks Qt for the style's own."""


def load_qlementine() -> ModuleType:
    """Import `qlementine`'s package for the Qt binding in use.

    Raises
    ------
    ImportError
        If the package cannot be imported, naming the extra that installs
        it and what the import said.
    """
    try:
        return importlib.import_module(MODULES[API])
    except ImportError as e:
        raise ImportError(
            f"QlementineStyle needs the package {MODULES[API]}, which "
            f"'redsun[{EXTRAS[API]}]' installs ({e})"
        ) from e


def name_of(style: QStyle | None) -> str:
    """Return the name *style* can be set again by, or nothing for a style that has none.

    Under a stylesheet the application's style is Qt's wrapper around the
    real one, and the wrapper has no name: the style it wraps, its child, is
    the one named.
    """
    if style is None:
        return ""
    wrapped = (child for child in style.children() if isinstance(child, QStyle))
    return style.objectName() or next((child.objectName() for child in wrapped), "")


def look_of(app: QApplication) -> Earlier:
    """Return the style, font and palette of *app*, as `restore` puts them back."""
    set_by_hand = app.testAttribute(QtNamespace.ApplicationAttribute.AA_SetPalette)
    return Earlier(
        name_of(app.style()), app.font(), app.palette() if set_by_hand else QPalette()
    )


def restore(app: QApplication, earlier: Earlier) -> None:
    """Give *app* back the style, font and palette of *earlier*."""
    if earlier.style:
        app.setStyle(earlier.style)
    app.setFont(earlier.font)
    app.setPalette(earlier.palette)


class QlementineStyle:
    """Gives the window `qlementine`'s look, dark or light as the colour scheme reads.

    A `configure_application` hook provider. It sets `qlementine`'s style on
    the application, in its dark or light theme for the current colour
    scheme, then changes theme at every change of the scheme, so the
    session's colour scheme control switches between the two. An unknown
    scheme gets the light theme.

    `qlementine` sets the application's font and palette as well. It also
    draws every icon in the window in one colour, that of the control the
    icon is on, so an icon whose colours carry a meaning loses them. At
    shutdown the application gets back the style, the font and the palette
    it had before; a style that has no name cannot be put back, and stays
    replaced.

    `qlementine`'s package is imported when the hook runs, so only a session
    that names this style needs it.
    """

    def __init__(self) -> None:
        self._app: QApplication | None = None
        self._earlier: Earlier | None = None
        self._follower: SchemeFollower | None = None
        self._style: Any = None
        self._themes: dict[bool, Any] = {}

    def configure_application(self, app: QApplication) -> None:
        """Set `qlementine`'s style on *app*, in the theme of the current colour scheme.

        A failure leaves the application as it was.

        Raises
        ------
        ImportError
            If `qlementine`'s package for the Qt binding in use cannot be
            imported.
        """
        qlementine = load_qlementine()
        self._themes = {
            True: qlementine.Theme.makeDark(),
            False: qlementine.Theme.makeLight(),
        }
        earlier = look_of(app)
        self._style = qlementine.QlementineStyle(app)
        # the palette gives ButtonText the colour of text on the style's
        # accent buttons, so an icon drawn in it vanishes on every other
        # button; the style colours each icon for the control it is on
        self._style.setAutoIconColor(qlementine.AutoIconColor.ForegroundColor)
        app.setStyle(self._style)
        try:
            self._follower = SchemeFollower(self._apply)
        except Exception:
            self._style = None
            restore(app, earlier)
            raise
        self._app, self._earlier = app, earlier

    def shutdown(self) -> None:
        """Stop following the colour scheme, and restore the previous style, font and palette."""
        if self._app is None or self._earlier is None or self._follower is None:
            return
        self._follower.stop()
        # the application deletes a style when it is given another
        self._style = None
        restore(self._app, self._earlier)
        self._app = None

    def _apply(self, dark: bool) -> None:
        if self._style is not None:
            self._style.setTheme(self._themes[dark])
