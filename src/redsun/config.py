"""Application-level configuration enums for redsun."""

from __future__ import annotations

from enum import Enum, unique

__all__ = [
    "FrontendTypes",
    "WidgetPositionTypes",
]


@unique
class FrontendTypes(str, Enum):
    """Supported frontend types.

    Attributes
    ----------
    PYQT : str
        PyQt6 frontend.
    PYSIDE : str
        PySide6 frontend.
    """

    PYQT = "pyqt"
    PYSIDE = "pyside"


@unique
class WidgetPositionTypes(str, Enum):
    """Supported widget position types.

    Used to define the position of a widget in the main view of the GUI.

    Attributes
    ----------
    CENTER : str
        Center widget position.
    LEFT : str
        Left widget position.
    RIGHT : str
        Right widget position.
    TOP : str
        Top widget position.
    BOTTOM : str
        Bottom widget position.
    """

    CENTER = "center"
    LEFT = "left"
    RIGHT = "right"
    TOP = "top"
    BOTTOM = "bottom"
