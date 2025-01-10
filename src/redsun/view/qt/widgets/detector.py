"""Qt detector settings widget module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pyqtgraph.parametertree import Parameter, ParameterTree
from qtpy import QtWidgets
from sunflare.view.qt import BaseQtWidget

if TYPE_CHECKING:
    from typing import Any

    from sunflare.config import ModelInfo, RedSunSessionInfo
    from sunflare.virtual import ModuleVirtualBus

    from redsun.controller.config import DetectorSettingsControllerInfo
    from redsun.virtual import HardwareVirtualBus


class DetectorSettingsWidget(BaseQtWidget):
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
        self._detectors_info: DetectorSettingsControllerInfo = config.controllers[
            "DetectorSettingsController"
        ]  # type: ignore

        self.tab = QtWidgets.QTabWidget()
        layout = QtWidgets.QVBoxLayout()

        # retrieve the models selected from the controller;
        # the content of _detectors_info.models is ensured to be
        # not None; we can skip type checking
        models_info = {
            model: self._config.models[model]
            for model in self._detectors_info.models  # type: ignore[union-attr]
        }

        for model_name, model_info in models_info.items():
            tree = self.build_params(model_info)
            self.tab.addTab(tree, model_name)

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
