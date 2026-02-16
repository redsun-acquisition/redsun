"""Redsun main view window."""

from __future__ import annotations

from typing import TYPE_CHECKING

from platformdirs import user_documents_dir
from qtpy import QtWidgets
from qtpy.QtCore import Qt
from sunflare.log import Loggable
from sunflare.virtual import VirtualAware

from redsun.config import WidgetPositionTypes

if TYPE_CHECKING:
    from sunflare.view import View
    from sunflare.virtual import VirtualBus


class QtMainView(QtWidgets.QMainWindow, Loggable):
    """Qt main window.

    Parameters
    ----------
    virtual_bus : VirtualBus
        Session virtual bus.
    session_name : str
        Display name for the window title.
    views : dict[str, PView]
        Dictionary of view name to pre-built view instance.
    """

    _DOCK_MAP = {
        WidgetPositionTypes.LEFT: Qt.DockWidgetArea.LeftDockWidgetArea,
        WidgetPositionTypes.RIGHT: Qt.DockWidgetArea.RightDockWidgetArea,
        WidgetPositionTypes.TOP: Qt.DockWidgetArea.TopDockWidgetArea,
        WidgetPositionTypes.BOTTOM: Qt.DockWidgetArea.BottomDockWidgetArea,
    }

    def __init__(
        self,
        virtual_bus: VirtualBus,
        session_name: str,
        views: dict[str, View],
    ) -> None:
        super().__init__()
        self.setWindowTitle(session_name)
        self._virtual_bus = virtual_bus
        self._central_widget_set = False
        self._widgets: dict[str, View] = {}
        self._dock_views(views)

        self._menu_bar = self.menuBar()
        assert self._menu_bar is not None
        file = self._menu_bar.addMenu("&File")
        assert file is not None

        self._save_action = QtWidgets.QAction("Save configuration as...", self)  # type: ignore[attr-defined]
        self._save_action.triggered.connect(self._save_configuration)
        file.addAction(self._save_action)

    def _dock_views(self, views: dict[str, View]) -> None:
        """Dock pre-built view instances into the main window.

        Views are docked according to a ``position`` attribute if
        available; otherwise the first unpositioned widget becomes the
        central widget.

        Parameters
        ----------
        views : dict[str, PView]
            Dictionary of view name to pre-built view instance.
        """
        for name, widget in views.items():
            self._widgets[name] = widget

            position = getattr(widget, "position", None)
            if position is not None and position != WidgetPositionTypes.CENTER:
                try:
                    dock_area = self._DOCK_MAP[WidgetPositionTypes(position)]
                    dock_widget = QtWidgets.QDockWidget(name)
                    dock_widget.setWidget(widget)  # type: ignore[arg-type]
                    self.addDockWidget(dock_area, dock_widget)
                except (KeyError, ValueError):
                    self.logger.error(f"Unknown position '{position}' for view: {name}")
            else:
                if not self._central_widget_set:
                    self.setCentralWidget(widget)  # type: ignore[arg-type]
                    self._central_widget_set = True
                else:
                    self.logger.error(f"Multiple central views are not allowed: {name}")

        self.setWindowState(Qt.WindowState.WindowMaximized)

    def connect_to_virtual(self) -> None:
        """Connect all views to the virtual layer."""
        for widget in self._widgets.values():
            if isinstance(widget, VirtualAware):
                widget.connect_to_virtual()

    def _save_configuration(self) -> None:
        """Save the current configuration."""
        from redsun.common.qt import ask_file_path

        path = ask_file_path(
            self,
            "Save configuration",
            "YAML (*.yaml *.yml)",
            folder=user_documents_dir(),
        )
        if path:
            self.logger.info(f"Configuration saved to {path}")
