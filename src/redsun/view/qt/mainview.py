"""RedSun main view window."""

from __future__ import annotations

from typing import TYPE_CHECKING

from qtpy.QtCore import Qt
from qtpy.QtWidgets import QDockWidget, QMainWindow

from redsun.view.qt.widgets import ImageViewWidget

from .widgets import DetectorSettingsWidget, MotorWidget

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
        self.setWindowTitle("RedSun")
        self._config = config
        self._virtual_bus = virtual_bus

        # image widget: center of the main window
        self._image_viewer: ImageViewWidget

        # device widgets: left side of the main window
        self._device_widgets: dict[str, BaseQtWidget] = {}

        # controller widgets: right side of the main window
        self._controller_widgets: dict[str, BaseQtWidget] = {}

        # custom widgets (need to be built)
        # TODO: build them; API
        self._widgets = widgets

    def build_view(self) -> None:
        """Build the main view window."""
        # build the device widgets

        if self._config.controllers["MotorController"] is not None:
            self._device_widgets["StepperMotor"] = MotorWidget(
                self._config, self._virtual_bus
            )

        if self._config.controllers["DetectorSettingsController"] is not None:
            self._device_widgets["DetectorSettings"] = DetectorSettingsWidget(
                self._config, self._virtual_bus
            )
            self._device_widgets["ImageView"] = ImageViewWidget(
                self._config, self._virtual_bus
            )

        # set dock widgets; the detector settings are on the top-left;
        # the stepper motor settings are below the detector settings;
        # the image viewer is set as the central widget;
        # TODO: give freedom to the user to choose the layout
        #       of the dock widgets
        if self._image_viewer is not None:
            self.setCentralWidget(self._image_viewer)
        if "DetectorSettings" in self._device_widgets.keys():
            dock = QDockWidget("Detector Settings", parent=self)
            dock.setWidget(self._device_widgets["DetectorSettings"])
            self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        if "ImageView" in self._device_widgets.keys():
            self.setCentralWidget(self._device_widgets["ImageView"])
        if "StepperMotor" in self._device_widgets.keys():
            dock = QDockWidget("Stepper Motor", parent=self)
            dock.setWidget(self._device_widgets["StepperMotor"])
            self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

        # after all the widgets are built, register the signals
        for widget in self._device_widgets.values():
            widget.registration_phase()

        self.setWindowState(Qt.WindowState.WindowMaximized)

    def connect_to_virtual(self) -> None:
        """Connect the view to the virtual layer."""
        for widget in self._device_widgets.values():
            widget.connection_phase()

        for widget in self._controller_widgets.values():
            widget.connection_phase()

        # TODO: to implement
        # for widget in self._widgets.values():
        #     widget.connection_phase()
