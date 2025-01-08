"""Qt detector settings widget module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pyqtgraph.parametertree import Parameter, ParameterTree
from qtpy import QtWidgets
from sunflare.view import WidgetProtocol

if TYPE_CHECKING:
    from typing import Any

    from sunflare.config import RedSunSessionInfo, ModelInfo
    from sunflare.virtual import ModuleVirtualBus

    from redsun.controller.config import DetectorControllerInfo
    from redsun.virtual import HardwareVirtualBus


class DetectorWidget(QtWidgets.QWidget, WidgetProtocol):
    """Detector settings widget class.

    Imports all detector configuration settings from the constructor and builds the widget based on the pydantic model's informations.

    A change in the displayed GUI values of the detector settings will be reflected in a change in the device settings.

    Each detector's settings is grouped in a QTabWidget.

    Parameters
    ----------
    config: RedSunSessionInfo
        Configuration options for the RedSun session.
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
        config: RedSunSessionInfo,
        virtual_bus: HardwareVirtualBus,
        module_bus: ModuleVirtualBus,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self._config = config
        self._virtual_bus = virtual_bus
        self._module_bus = module_bus

        self._detectors_info: dict[str, Any] = {}
        ctrl_info: DetectorControllerInfo = config.controllers["DetectorController"]  # type: ignore
        if ctrl_info.models is not None:
            self._detectors_info = {
                name: {
                    "exposure_egu": ctrl_info.egus,
                }
                for name in ctrl_info.models
            }

        self.tab = QtWidgets.QTabWidget()

        layout = QtWidgets.QVBoxLayout()

        for detector_name, detector_info in self._detectors_info.items():
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
    def build_params(self, detector_info: ModelInfo) -> ParameterTree:
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
        ]
        parameter = Parameter.create(
            name="Detector parameters", type="group", children=params
        )
        tree = ParameterTree()
        tree.setParameters(parameter, showTop=True)
        return tree
