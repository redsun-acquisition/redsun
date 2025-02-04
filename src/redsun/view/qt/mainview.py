"""RedSun main view window."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from qtpy import QtWidgets
from qtpy.QtCore import Qt
from sunflare.config import WidgetPositionTypes
from sunflare.log import Loggable

if TYPE_CHECKING:
    from sunflare.config import RedSunSessionInfo
    from sunflare.view.qt import BaseQtWidget
    from sunflare.virtual import VirtualBus

from redsun.common.qt import ask_file_path


class RedSunMainWindow(QtWidgets.QMainWindow, Loggable):
    """RedSun main window.

    Parameters
    ----------
    virtual_bus : :class:`~sunflare.virtual.VirtualBus`
        Session virtual bus.
    config : :class:`~sunflare.config.RedSunSessionInfo`
        Session configuration.
    widgets : dict[str, type[:class:`~sunflare.view.qt.BaseQtWidget`]]
        Dictionary with the widget names and their types.
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
        config: RedSunSessionInfo,
        widgets: dict[str, type[BaseQtWidget]],
    ) -> None:
        super().__init__()
        self.setWindowTitle(config.session)
        self._config = config
        self._virtual_bus = virtual_bus

        self._widgets: dict[str, BaseQtWidget] = {}
        self.build_view(widgets)

        self._menu_bar: QtWidgets.QMenuBar

        # making mypy happy with qtpy is hard
        self._menu_bar = cast(QtWidgets.QMenuBar, self.menuBar())
        file = cast(QtWidgets.QMenu, self._menu_bar.addMenu("&File"))

        # apparently importing QAction from qtpy
        # is a mess, so we'll keep mypy silent
        self._save_action = QtWidgets.QAction("Save configuration as...", self)  # type: ignore[attr-defined]
        self._save_action.triggered.connect(self._save_configuration)
        file.addAction(self._save_action)

    def build_view(self, widget_types: dict[str, type[BaseQtWidget]]) -> None:
        """Build the main view window.

        Iterates over `widget_types` and creates the widgets.
        The widgets are docked according to the associated value of
        ``config.widgets[widget_name].position``. If said value is
        :class:`~sunflare.config.WidgetPositionTypes.CENTER`,
        the widget is set as the central widget.

        Parameters
        ----------
        widget_types : ``dict[str, type[BaseQtWidget]]``
            Dictionary with the widget names and their types.
        """
        for name, widget_type in widget_types.items():
            widget = widget_type(self._config, self._virtual_bus)
            self._widgets[name] = widget
            try:
                cfg = self._config.widgets[name]
                dock_area = self._DOCK_MAP[cfg.position]
                dock_widget = QtWidgets.QDockWidget(name, widget)
                self.addDockWidget(dock_area, dock_widget)
            except KeyError:
                # assuming that current widget
                # should be set as central widget
                if self.centralWidget() is None:
                    self.setCentralWidget(widget)
                else:
                    self.error(f"Multiple central widgets are not allowed: {name}")
            widget.registration_phase()
            self._widgets[name] = widget

        self.setWindowState(Qt.WindowState.WindowMaximized)

    def connect_to_virtual(self) -> None:
        """Connect the view to the virtual layer.

        Iterates over all widgets and calls their `connection_phase` method.
        """
        for widget in self._widgets.values():
            widget.connection_phase()

    def _save_configuration(self) -> None:
        """Save the current configuration."""
        path = ask_file_path(
            self,
            "Save configuration",
            "YAML (*.yaml *.yml)",
        )
        if path:
            self._config.store_yaml(path)
            self.info(f"Configuration saved to {path}")
