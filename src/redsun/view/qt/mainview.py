"""RedSun main view window."""

from __future__ import annotations

from typing import TYPE_CHECKING, Type

from qtpy.QtCore import Qt
from qtpy.QtWidgets import QDockWidget, QMainWindow
from sunflare.config import MotorModelTypes

from redsun.view.qt.widgets import ImageViewWidget

from .widgets import DetectorSettingsWidget, StepperMotorWidget

if TYPE_CHECKING:
    from sunflare.config import RedSunInstanceInfo
    from sunflare.view.qt import BaseWidget
    from sunflare.virtual import ModuleVirtualBus

    from redsun.virtual import HardwareVirtualBus


class RedSunMainWindow(QMainWindow):
    """RedSun main window.

    Parameters
    ----------
    controller : RedsunMainHardwareController
        RedSun main hardware controller. Contains all the references to the backend objects.
    """

    def __init__(
        self,
        virtual_bus: HardwareVirtualBus,
        module_bus: ModuleVirtualBus,
        config: RedSunInstanceInfo,
        widgets: dict[str, Type[BaseWidget]],
    ) -> None:
        super().__init__()
        self.setWindowTitle("RedSun")
        self._config = config
        self._virtual_bus = virtual_bus
        self._module_bus = module_bus

        # image widget: center of the main window
        self._image_viewer: ImageViewWidget

        # device widgets: left side of the main window
        self._device_widgets: dict[str, BaseWidget] = {}

        # controller widgets: right side of the main window
        self._controller_widgets: dict[str, BaseWidget] = {}

        # custom widgets (need to be built)
        # TODO: build them; API
        self._widgets = widgets

    def build_view(self) -> None:
        """Build the main view window."""
        # build the device widgets

        motors_info = {
            name: info
            for name, info in self._config.motors.items()
            if info.category == MotorModelTypes.STEPPER
        }
        if motors_info:
            self._device_widgets["StepperMotor"] = StepperMotorWidget(
                self._config, self._virtual_bus, self._module_bus
            )

        # TODO: the model info should provide a flag to indicate
        #       if the detector is supposed to be added to the GUI
        if self._config.detectors:
            self._device_widgets["DetectorSettings"] = DetectorSettingsWidget(
                self._config,
                self._virtual_bus,
                self._module_bus,
            )
            self._device_widgets["ImageView"] = ImageViewWidget(
                self._config, self._virtual_bus, self._module_bus
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
