"""qlementine's look for a Qt session, following its colour scheme."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any, NamedTuple

from qtpy import API
from qtpy.QtCore import Qt as QtNamespace
from qtpy.QtGui import QPalette

from ._scheme import SchemeFollower

if TYPE_CHECKING:
    from types import ModuleType

    from qtpy.QtGui import QFont
    from qtpy.QtWidgets import QApplication

__all__ = ["QlementineStyle"]

MODULES = {"pyqt6": "PyQt6Qlementine", "pyside6": "PySide6Qlementine"}
"""The package holding qlementine for each Qt binding."""

EXTRAS = {"pyqt6": "qlementine-pyqt", "pyside6": "qlementine-pyside"}
"""The extra of `redsun` that installs the package, for each Qt binding."""

THEME_PATH = ":/qlementine/resources/themes/{}.json"
"""Where qlementine's package keeps its theme of a given name."""


class Earlier(NamedTuple):
    """How the application looked before the style."""

    style: str
    """The name of its style; empty for a style that has none."""

    font: QFont
    """Its font."""

    palette: QPalette
    """Its palette if one had been set on it, or else an empty one, which asks Qt for the style's own."""


def load_qlementine() -> ModuleType:
    """Import qlementine's package for the Qt binding in use.

    Raises
    ------
    ImportError
        If the package is not installed, naming the extra that installs it.
    """
    try:
        return importlib.import_module(MODULES[API])
    except ImportError as e:
        raise ImportError(
            f"QlementineStyle needs the package {MODULES[API]}, which "
            f"'redsun[{EXTRAS[API]}]' installs"
        ) from e


class QlementineStyle:
    """Gives the window qlementine's look, dark or light as the colour scheme reads.

    A `configure_application` hook provider. It sets qlementine's style on
    the application, in its dark or light theme for the current colour
    scheme, then changes theme at every change of the scheme, so the
    session's colour scheme control switches between the two. An unknown
    scheme gets the light theme. qlementine sets the application's font and
    palette as well, and draws each icon in the colour of the control it is
    on. At shutdown the application gets back the style, the
    font and the palette it had before; a style it held without a name
    cannot be put back, and stays replaced.

    qlementine's package is imported when the hook runs, so only a session
    that names this style needs it.
    """

    def __init__(self) -> None:
        self._app: QApplication | None = None
        self._earlier: Earlier | None = None
        self._follower: SchemeFollower | None = None
        self._style: Any = None
        self._themes: dict[bool, Any] = {}

    def configure_application(self, app: QApplication) -> None:
        """Set qlementine's style on *app*, in the theme of the current colour scheme.

        Raises
        ------
        ImportError
            If qlementine's package for the Qt binding in use is not
            installed.
        """
        qlementine = load_qlementine()
        # read before anything changes, so a failure above leaves no trace
        self._themes = {
            dark: qlementine.Theme.fromJsonPath(THEME_PATH.format(name))
            for dark, name in ((True, "dark"), (False, "light"))
        }
        style = app.style()
        set_by_hand = app.testAttribute(QtNamespace.ApplicationAttribute.AA_SetPalette)
        self._earlier = Earlier(
            style.objectName() if style is not None else "",
            app.font(),
            app.palette() if set_by_hand else QPalette(),
        )
        self._style = qlementine.QlementineStyle(app)
        # qlementine's palette gives ButtonText the colour of text on its
        # accent buttons, so an icon drawn in it vanishes on every other
        # button; the style colours each icon for the control it is on
        self._style.setAutoIconColor(qlementine.AutoIconColor.ForegroundColor)
        app.setStyle(self._style)
        self._app = app
        self._follower = SchemeFollower(self._apply)

    def shutdown(self) -> None:
        """Stop following the colour scheme, and restore the previous style, font and palette."""
        if self._app is None or self._earlier is None or self._follower is None:
            return
        self._follower.stop()
        # the application deletes a style when it is given another
        self._style = None
        if self._earlier.style:
            self._app.setStyle(self._earlier.style)
        self._app.setFont(self._earlier.font)
        self._app.setPalette(self._earlier.palette)
        self._app = None

    def _apply(self, dark: bool) -> None:
        if self._style is not None:
            self._style.setTheme(self._themes[dark])
