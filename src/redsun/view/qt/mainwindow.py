# noqa: D100
from typing import TYPE_CHECKING
from qtpy.QtWidgets import QMainWindow

if TYPE_CHECKING:
    from sunflare.config import RedSunInstanceInfo


class RedSunMainWindow(QMainWindow):  # noqa: D101
    def __init__(self, config: "RedSunInstanceInfo") -> None:
        super().__init__()
