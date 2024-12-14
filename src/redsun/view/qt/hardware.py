# noqa: D100
from __future__ import annotations

from qtpy.QtWidgets import QMainWindow

from sunflare.log import Loggable


class RedSunMainHardwareWidget(QMainWindow, Loggable):  # noqa: D101
    """RedSun main hardware widget."""

    def __init__(self, title: str) -> None:
        super().__init__()
