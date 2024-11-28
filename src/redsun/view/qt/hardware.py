# noqa: D100
from typing import TYPE_CHECKING
from qtpy.QtWidgets import QMainWindow

from sunflare.log import Loggable

if TYPE_CHECKING:
    from sunflare.config import RedSunInstanceInfo

    from typing import Any


class RedSunMainHardwareWidget(QMainWindow, Loggable):  # noqa: D101
    def __init__(
        self, title: str, config: "RedSunInstanceInfo", *args: "Any", **kwargs: "Any"
    ) -> None:
        super().__init__(*args, **kwargs)
