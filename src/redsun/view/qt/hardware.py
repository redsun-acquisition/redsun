# noqa: D100
from __future__ import annotations

from typing import TYPE_CHECKING
from qtpy.QtWidgets import QMainWindow

from sunflare.log import Loggable

if TYPE_CHECKING:
    from sunflare.config import RedSunInstanceInfo


class RedSunMainHardwareWidget(QMainWindow, Loggable):  # noqa: D101
    """RedSun main hardware widget."""

    def __init__(self, title: str, config: RedSunInstanceInfo) -> None:
        super().__init__()
