# noqa: D104
import sys
from typing import NoReturn

from qtpy.QtWidgets import QApplication

from redsun.controller.hardware import RedsunMainHardwareController

from .mainview import RedSunMainWindow

__all__ = ["RedSunMainWindow"]


def build_view_layer(controller: RedsunMainHardwareController) -> NoReturn:
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
    view = RedSunMainWindow(controller)
    view.build_view()
    view.show()
    sys.exit(app.exec())
