"""RedSun main view window."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qtpy.QtCore import Qt
from qtpy.QtWidgets import QMainWindow

if TYPE_CHECKING:
    from sunflare.config import RedSunSessionInfo
    from sunflare.view.qt import BaseQtWidget
    from sunflare.virtual import VirtualBus


class RedSunMainWindow(QMainWindow):
    """RedSun main window.

    Parameters
    ----------
    controller : RedsunMainHardwareController
        RedSun main hardware controller. Contains all the references to the backend objects.
    """

    def __init__(
        self,
        virtual_bus: VirtualBus,
        config: RedSunSessionInfo,
        widgets: dict[str, type[BaseQtWidget]],
    ) -> None:
        super().__init__()
        self.setWindowTitle(config.session)
        self._config = config
        self._virtual_bus = virtual_bus

        # custom widgets (need to be built)
        # TODO: build them; API
        self._widgets = widgets

    def build_view(self) -> None:
        """Build the main view window."""
        # TODO: build the widgets here

        self.setWindowState(Qt.WindowState.WindowMaximized)

    def connect_to_virtual(self) -> None:
        """Connect the view to the virtual layer."""
