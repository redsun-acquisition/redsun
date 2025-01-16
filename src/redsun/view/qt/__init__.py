import sys
from typing import NoReturn, cast

from qtpy.QtWidgets import QApplication
from sunflare.config import RedSunSessionInfo
from sunflare.view import WidgetProtocol
from sunflare.view.qt import BaseQtWidget
from sunflare.virtual import VirtualBus

from .mainview import RedSunMainWindow
from .utils import ProcessEventsDuringTask

__all__ = [
    "RedSunMainWindow",
    "build_view_layer",
    "launch_app",
    "create_app",
    "ProcessEventsDuringTask",
]


def build_view_layer(
    config: RedSunSessionInfo,
    widgets: dict[str, type[WidgetProtocol]],
    virtual_bus: VirtualBus,
) -> RedSunMainWindow:
    """Build the view layer.

    Creates the main application that will run the GUI, and the main window (which will also, in
    turn, allocate all the necessary widgets required to respect the active configuration).

    The GUI is not yet started, as we still need to connect the controller and the view
    to the virtual layer.

    Parameters
    ----------
    config : RedSunSessionInfo
        RedSun configuration.
    widgets : dict[str, type[WidgetProtocol]]
        Dictionary of widgets.
    """
    # cast to make type checker happy; the assumption is that
    # build_view_layer is selected based on the frontend type
    qt_widgets = cast(dict[str, type[BaseQtWidget]], widgets)
    view = RedSunMainWindow(virtual_bus, config, qt_widgets)
    view.build_view()
    return view


def create_app() -> QApplication:
    """Create the main application."""
    return QApplication([])


def launch_app(app: QApplication, view: RedSunMainWindow) -> NoReturn:
    """Launch the application.

    Parameters
    ----------
    app : QApplication
        The main application.
    view : RedSunMainWindow
        The main window.
    """
    view.show()
    sys.exit(app.exec())
