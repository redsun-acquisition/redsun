"""Qt detector settings widget module."""

from __future__ import annotations
from typing import TYPE_CHECKING

from sunflare.view.qt import BaseWidget
from sunflare.virtualbus import VirtualBus

from qtpy import QtWidgets

if TYPE_CHECKING:
    from redsun.controller.virtualbus import HardwareVirtualBus

    from sunflare.config import DetectorModelInfo
    from sunflare.virtualbus import VirtualBus

    from pyqtgraph.parametertree import Parameter, ParameterTree


class DetectorSettingsWidget(BaseWidget):
    """Detector settings widget class.

    Imports all detector configuration settings from the constructor and builds the widget based on the pydantic model's informations.

    A change in the displayed GUI values of the detector settings will be reflected in a change in the device settings.

    Each detector's settings is grouped in a QTabWidget.

    Parameters
    ----------
    detectors_info: dict[str, DetectorModelInfo]
        Dictionary of currently available detector models.
    virtual_bus : HardwareVirtualBus
        The virtual bus instance for the RedSun instance.
    module_bus : VirtualBus
        The inter-module virtual bus instance.
    """

    _virtual_bus: HardwareVirtualBus

    def __init__(
        self,
        detectors_info: dict[str, DetectorModelInfo],
        virtual_bus: HardwareVirtualBus,
        module_bus: VirtualBus,
    ) -> None:
        super().__init__(virtual_bus, module_bus)
        self._detectors_info = detectors_info

        self.tab = QtWidgets.QTabWidget()

        layout = QtWidgets.QVBoxLayout()

        for detector_name, detector_info in detectors_info.items():
            tree = self.build_params(detector_info)
            self.tab.addTab(tree, detector_name)

        layout.addWidget(self.tab)
        self.setLayout(layout)

    def registration_phase(self) -> None:  # noqa: D102
        # nothing to do here
        ...

    def connection_phase(self) -> None:  # noqa: D102
        # nothing to do here... for now
        ...

    # TODO: parameter grouping needs review
    # TODO: generalize for all parameter groups
    def build_params(self, detector_info: DetectorModelInfo) -> ParameterTree:
        """Build a parameter tree for the detector settings.

        Parameters
        ----------
        detector_info : DetectorModelInfo
            The detector model information.

        Returns
        -------
        ParameterTree
            The parameter tree for the detector settings.
        """
        params = [
            {
                "name": "Model Name",
                "type": "str",
                "value": detector_info.model_name,
                "readonly": True,
            },
            {
                "name": "Supported Engines",
                "type": "list",
                "value": detector_info.supported_engines[0],
                "readonly": True,
            },
            {
                "name": "Vendor",
                "type": "str",
                "value": detector_info.vendor,
                "readonly": True,
            },
            {
                "name": "Serial Number",
                "type": "str",
                "value": detector_info.serial_number,
                "readonly": True,
            },
            {
                "name": "Category",
                "type": "str",
                "value": detector_info.category,
                "readonly": True,
            },
            {
                "name": "Sensor Size",
                "type": "str",
                "value": str(detector_info.sensor_size),
                "readonly": True,
            },
            {
                "name": "Pixel Size",
                "type": "str",
                "value": str(detector_info.pixel_size),
            },
            {
                "name": "Exposure EGU",
                "type": "str",
                "value": detector_info.exposure_egu,
            },
        ]
        parameter = Parameter.create(
            name="Detector parameters", type="group", children=params
        )
        tree = ParameterTree()
        tree.setParameters(parameter, showTop=True)
        return tree
