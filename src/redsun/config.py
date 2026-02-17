"""Application-level configuration enums for redsun."""

from __future__ import annotations

from enum import Enum, unique

__all__ = [
    "FrontendTypes",
    "ViewPositionTypes",
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
class ViewPositionTypes(str, Enum):
    """Supported view position types.

    Used to define the position of a view component in the main view of the GUI.

    !!! warning
        These values are based on how Qt manages dock widgets.
        They may change in the future.

    Attributes
    ----------
    CENTER : str
        Center view position.
    LEFT : str
        Left view position.
    RIGHT : str
        Right view position.
    TOP : str
        Top view position.
    BOTTOM : str
        Bottom view position.
    """

    CENTER = "center"
    LEFT = "left"
    RIGHT = "right"
    TOP = "top"
    BOTTOM = "bottom"
