from enum import Enum, unique

from ._base import PView, View

__all__ = ["PView", "View", "ViewPosition"]


@unique
class ViewPosition(str, Enum):
    """Where a view sits in the main window.

    !!! warning
        The values follow Qt's dock widget areas and may change.
    """

    CENTER = "center"
    LEFT = "left"
    RIGHT = "right"
    TOP = "top"
    BOTTOM = "bottom"
