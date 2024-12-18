"""RedSun main view window."""

from __future__ import annotations

from qtpy.QtWidgets import QMainWindow, QDockWidget
from qtpy.QtCore import Qt

from .widgets import StepperMotorWidget, DetectorSettingsWidget

from redsun.view.qt.widgets import ImageViewWidget

from sunflare.config import MotorModelTypes

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redsun.controller.hardware import RedsunMainHardwareController


class RedSunMainWindow(QMainWindow):
    """RedSun main window.

    Parameters
    ----------
    controller : RedsunMainHardwareController
        RedSun main hardware controller. Contains all the references to the backend objects.
    """

    def __init__(self, controller: RedsunMainHardwareController) -> None:
        super().__init__()
        self.setWindowTitle("RedSun")

        self._controller = controller
        # image widget: center of the main window
        self._image_viewer: ImageViewWidget

        # device widgets: left side of the main window
        self._device_widgets: dict[str, QDockWidget] = {}

        # controller widgets: right side of the main window
        self._controller_widgets: dict[str, QDockWidget] = {}

    def build_view(self) -> None:
        """Build the main view window."""
        # build the device widgets
        registry = self._controller.device_registry
        motors_info = {
            motor.name: motor.model_info
            for motor in registry.motors.values()
            if motor.model_info.category == MotorModelTypes.STEPPER
        }
        if motors_info:
            stepper_widget = StepperMotorWidget(
                motors_info, self._controller.virtual_bus, self._controller.module_bus
            )
            stepper_widget.registration_phase()

        # TODO: the model info should provide a flag to indicate
        #       if the detector is supposed to be added to the GUI
        detectors_info = {
            detector.name: detector.model_info
            for detector in registry.detectors.values()
        }
        if detectors_info:
            detector_widget = DetectorSettingsWidget(
                detectors_info,
                self._controller.virtual_bus,
                self._controller.module_bus,
            )
            detector_widget.registration_phase()
            self._image_viewer = ImageViewWidget(
                self._controller.virtual_bus, self._controller.module_bus
            )
            self._image_viewer.registration_phase()

        # set dock widgets; the detector settings are on the top-left;
        # the stepper motor settings are below the detector settings;
        # the image viewer is set as the central widget;
        # TODO: give freedom to the user to choose the layout
        #       of the dock widgets
        if self._image_viewer is not None:
            self.setCentralWidget(self._image_viewer)
        if detector_widget is not None:
            self._device_widgets["detector"] = QDockWidget("Detector", parent=self)
            self._device_widgets["detector"].setWidget(detector_widget)
            self.addDockWidget(
                Qt.DockWidgetArea.LeftDockWidgetArea, self._device_widgets["detector"]
            )
        if stepper_widget is not None:
            self._device_widgets["stepper"] = QDockWidget("Stepper", parent=self)
            self._device_widgets["stepper"].setWidget(stepper_widget)
            self.addDockWidget(
                Qt.DockWidgetArea.LeftDockWidgetArea, self._device_widgets["stepper"]
            )

        self.setWindowState(Qt.WindowState.WindowMaximized)
