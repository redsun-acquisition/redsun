import sys
from typing import NoReturn, Type, Tuple

from qtpy.QtWidgets import QApplication
from sunflare.config import RedSunInstanceInfo
from sunflare.view.qt import BaseWidget
from .mainview import RedSunMainWindow

__all__ = ["RedSunMainWindow", "build_view_layer", "launch_app"]


def build_view_layer(
    config: RedSunInstanceInfo, widgets: dict[str, Type[BaseWidget]]
) -> Tuple[QApplication, RedSunMainWindow]:
    """Build the view layer.

    Creates the main application that will run the GUI, and the main window (which will also, in
    turn, allocate all the necessary widgets required to respect the active configuration).

    The GUI is not yet started, as we still need to connect the controller and the view
    to the virtual layer.

    Parameters
    ----------
    config : RedSunInstanceInfo
        RedSun configuration.
    widgets : dict[str, Type[BaseWidget]]
        The built widgets.
    """
    app = QApplication([])
    view = RedSunMainWindow(config, widgets)
    view.build_view()
    return app, view


def launch_app(app: QApplication, view: RedSunMainWindow) -> NoReturn:
    """Launch the application.

    Parameters
    ----------
    app : QApplication
        The main application.
    view : RedSunMainWindow
        The main window.
    controller : RedSunMainHardwareController
        The main hardware controller.
    """
    view.show()
    sys.exit(app.exec())
