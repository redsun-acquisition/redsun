"""Redsun main hardware controller module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sunflare.controller import HasConnection, HasRegistration
from sunflare.log import Loggable

from redsun.controller.factory import BackendFactory

if TYPE_CHECKING:
    from sunflare.config import RedSunSessionInfo
    from sunflare.controller import ControllerProtocol
    from sunflare.model import ModelProtocol
    from sunflare.virtual import VirtualBus

    from redsun.plugins import PluginTypeDict


class RedsunController(Loggable):
    """Redsun main hardware controller.

    Parameters
    ----------
    config : RedSunSessionInfo
        Redsun configuration.
    virtual_bus : HardwareVirtualBus
        Hardware virtual bus.
    module_bus : ModuleVirtualBus
        Module virtual bus.
    classes : Backend
        Dictionary of factory classes for devices and controllers.
    """

    def __init__(
        self,
        config: RedSunSessionInfo,
        virtual_bus: VirtualBus,
        classes: PluginTypeDict,
    ):
        self.config = config
        self.virtual_bus = virtual_bus
        self.classes = classes
        self.models: dict[str, ModelProtocol] = {}
        self.controllers: dict[str, ControllerProtocol] = {}

    def build_layer(self) -> None:
        """Build the controller layer.

        The method builds the full controller layer in a bottom-up fashion:

        - build the engine handler;
        - build the device models;
        - build the controllers;
        - build the storage backend (currently not implemented).

        After all objects are build, the registration phase occurs and all signals that are intended to be
        exposed to the virtual buses are registered accordingly to the hardware or module virtual bus.

        During the building of the models and controllers, an error may occur if the configuration
        file is not correct. The error caused by the creation of that specific object is logged,
        the creation is skipped, and the process continues with the next object.
        """
        models_info = self.config.models
        controllers_info = self.config.controllers

        # build models
        for model_name, model_info in models_info.items():
            model_class = self.classes["models"][model_name]
            model_obj = BackendFactory.build_model(
                name=model_name,
                model_class=model_class,
                model_info=model_info,
            )
            if model_obj is None:
                continue
            self.models[model_name] = model_obj

        # build controllers
        for ctrl_name, ctrl_info in controllers_info.items():
            ctrl_class = self.classes["controllers"][ctrl_name]
            controller = BackendFactory.build_controller(
                name=ctrl_name,
                ctrl_info=ctrl_info,
                ctrl_class=ctrl_class,
                models=self.models,
                virtual_bus=self.virtual_bus,
            )
            if controller is None:
                continue
            self.controllers[ctrl_name] = controller

        # register any sender controller
        for ctrl in self.controllers.values():
            if isinstance(ctrl, HasRegistration):
                ctrl.registration_phase()

    def connect_to_virtual(self) -> None:
        """Connect any receiver controller to the virtual bus."""
        for ctrl in self.controllers.values():
            if isinstance(ctrl, HasConnection):
                ctrl.connection_phase()
