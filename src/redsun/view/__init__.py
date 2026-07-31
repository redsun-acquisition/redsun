from enum import Enum, unique

from ._base import PView, View

__all__ = ["PView", "View", "ViewPosition"]


@unique
class ViewPosition(str, Enum):
    """Supported view positions.

    Where a view component sits in the main window.

    !!! warning
        These values are based on how Qt manages dock widgets.
        They may change in the future.
    """

    CENTER = "center"
    LEFT = "left"
    RIGHT = "right"
    TOP = "top"
    BOTTOM = "bottom"
