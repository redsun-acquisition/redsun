"""Redsun main view window."""

from __future__ import annotations

from typing import TYPE_CHECKING

from platformdirs import user_documents_dir
from qtpy import QtWidgets
from qtpy.QtCore import Qt
from sunflare.log import Loggable
from sunflare.view import ViewPosition

if TYPE_CHECKING:
    from sunflare.view.qt import QtView
    from sunflare.virtual import VirtualContainer

__all__ = ["QtMainView"]


class QtMainView(QtWidgets.QMainWindow, Loggable):
    """Qt main window.

    Parameters
    ----------
    virtual_container : VirtualContainer
        Session virtual container.
    session_name : str
        Display name for the window title.
    views : dict[str, QtView]
        Dictionary of view name to pre-built view instance.
    """

    _DOCK_MAP = {
        ViewPosition.LEFT: Qt.DockWidgetArea.LeftDockWidgetArea,
        ViewPosition.RIGHT: Qt.DockWidgetArea.RightDockWidgetArea,
        ViewPosition.TOP: Qt.DockWidgetArea.TopDockWidgetArea,
        ViewPosition.BOTTOM: Qt.DockWidgetArea.BottomDockWidgetArea,
    }

    def __init__(
        self,
        virtual_container: VirtualContainer,
        session_name: str,
        views: dict[str, QtView],
    ) -> None:
        super().__init__()
        self.setWindowTitle(session_name)
        self._virtual_container = virtual_container
        self._widgets: dict[str, QtView] = {}
        self._dock_views(views)

        self._menu_bar = self.menuBar()
        assert self._menu_bar is not None
        self._file = self._menu_bar.addMenu("&File")
        assert self._file is not None

        self._save_action = QtWidgets.QAction("Save configuration as...", self)  # type: ignore[attr-defined]
        self._save_action.triggered.connect(self._save_configuration)
        self._file.addAction(self._save_action)

    def _dock_views(self, views: dict[str, QtView]) -> None:
        """Dock pre-built view instances into the main window.

        Views are docked according to a ``position`` attribute if
        available; otherwise the first unpositioned widget becomes the
        central widget.

        Parameters
        ----------
        views : dict[str, QtView]
            Dictionary of view name to pre-built view instance.
        """
        centers: set[QtView] = set()

        for name, widget in views.items():
            widget.setObjectName(name)
            try:
                if widget.view_position == ViewPosition.CENTER:
                    # stash the center widgets to add them
                    # as a tab widget if there are multiple
                    centers.add(widget)
                    continue
                dock_area = self._DOCK_MAP[widget.view_position]
                dock_widget = QtWidgets.QDockWidget(name)
                dock_widget.setWidget(widget)
                self.addDockWidget(dock_area, dock_widget)
            except (AttributeError, KeyError):
                self.logger.error(
                    f"View '{name}' does not have a valid position and will not be shown."
                    "Ensure the view has a 'view_position' attribute set to a valid ViewPosition value."
                )
        if len(centers) == 0:
            # no center widgets, do nothing
            pass
        elif len(centers) > 1:
            center_tab = QtWidgets.QTabWidget()
            for widget in centers:
                center_tab.addTab(widget, widget.objectName())
            self.setCentralWidget(center_tab)
        else:
            # only one center widget, add it directly
            self.setCentralWidget(centers.pop())

        # TODO: this should be customizable by the user
        self.setWindowState(Qt.WindowState.WindowMaximized)

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
