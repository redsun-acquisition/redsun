"""A Qt view the layout and window tests dock."""

from __future__ import annotations

from qtpy.QtWidgets import QWidget

from redsun import Placement
from redsun.qt import Dock


class Panel(QWidget):
    """A view docked on the left."""

    placement: Placement = Dock("left")

    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.name = name
