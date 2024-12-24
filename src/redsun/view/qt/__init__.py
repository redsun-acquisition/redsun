import sys
from typing import NoReturn, Type

from qtpy.QtWidgets import QApplication
from sunflare.config import RedSunInstanceInfo
from sunflare.view.qt import BaseWidget

from .mainview import RedSunMainWindow

__all__ = ["build_view_layer"]


def build_view_layer(
    config: RedSunInstanceInfo, widgets: dict[str, Type[BaseWidget]]
) -> NoReturn:
    """Build the view layer.

    This function is dual-purpose: it creates the main QApplication that will run the GUI, and it also
    builds the main window (which will also, in turn, allocate all the necessary widgets required
    to respect the active configuration).

    When the view layer is built, the main window is shown and the GUI is started. This function
    is blocking and will only return when the GUI is closed.

    Parameters
    ----------
    controller : RedsunMainHardwareController
        RedSun main hardware controller.
    """
    app = QApplication([])
    view = RedSunMainWindow(config, widgets)
    view.build_view()
    view.show()
    sys.exit(app.exec())
