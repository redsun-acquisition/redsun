from enum import Enum, unique

from ._base import PView, View

__all__ = ["PView", "View", "ViewPosition"]


@unique
class ViewPosition(str, Enum):
    """Supported view positions.

    Used to define the position of a view component in the main view of the UI.

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
