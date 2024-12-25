import sys
from typing import NoReturn, Type

from qtpy.QtWidgets import QApplication
from sunflare.config import RedSunInstanceInfo
from sunflare.view.qt import BaseWidget
from sunflare.virtualbus import ModuleVirtualBus

from redsun.virtual import HardwareVirtualBus

from .mainview import RedSunMainWindow
from .utils import ProcessEventsDuringTask

__all__ = [
    "RedSunMainWindow",
    "build_view_layer",
    "launch_app",
    "create_app",
    "BaseWidget",
    "ProcessEventsDuringTask",
]


def build_view_layer(
    config: RedSunInstanceInfo,
    widgets: dict[str, Type[BaseWidget]],
    virtual_bus: HardwareVirtualBus,
    module_bus: ModuleVirtualBus,
) -> RedSunMainWindow:
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
    view = RedSunMainWindow(virtual_bus, module_bus, config, widgets)
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
