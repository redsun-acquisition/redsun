"""Redsun main hardware controller module."""

from __future__ import annotations

from typing import TYPE_CHECKING, Type, Union

from sunflare.log import Loggable
from sunflare.config import DetectorModelInfo, MotorModelInfo, RedSunInstanceInfo
from sunflare.engine.detector import DetectorModel
from sunflare.engine.motor import MotorModel

from .factory import Factory

if TYPE_CHECKING:
    from sunflare.controller import BaseController
    from sunflare.virtualbus import ModuleVirtualBus

    from redsun.virtual import HardwareVirtualBus

ModelTypes = Union[
    Type[DetectorModel[DetectorModelInfo]],
    Type[MotorModel[MotorModelInfo]],
]


class RedSunMainHardwareController(Loggable):
    """RedSun main hardware controller.

    Parameters
    ----------
    config : RedSunInstanceInfo
        RedSun configuration.
    virtual_bus : HardwareVirtualBus
        Hardware virtual bus.
    module_bus : ModuleVirtualBus
        Module virtual bus.
    models : dict[str, Union[Type[MotorModel], Type[DetectorModel]]]
        The built models.
    controllers : dict[str, BaseController]
        The built controllers.
    """

    def __init__(
        self,
        config: RedSunInstanceInfo,
        virtual_bus: HardwareVirtualBus,
        module_bus: ModuleVirtualBus,
        models: dict[str, Union[Type[MotorModel], Type[DetectorModel]]],
        controllers: dict[str, BaseController],
    ):
        self.config = config
        self.virtual_bus = virtual_bus
        self.module_bus = module_bus
        self.models = models
        self.controllers = controllers

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
        handler = Factory.build_handler(
            self.config.engine, self.virtual_bus, self.module_bus
        )
        if handler is None:
            # TODO: the application should quit here;
            #       without the handler the application cannot run
            return

        # build motors
        for (motor_name, motor_info), motor_model in zip(
            self.config.motors.items(), self.models["motors"]
        ):
            motor_model = Factory.build_model(
                name=motor_name, model_class=motor_model, model_info=motor_info
            )
            if motor_model is None:
                continue
            handler.motors[motor_name] = motor_model

        # build detectors
        for (det_name, det_info), det_model in zip(
            self.config.detectors.items(), self.models["detectors"]
        ):
            detector_model = Factory.build_model(
                name=det_name,
                model_class=det_model,
                model_info=det_info,
            )
            if detector_model is None:
                continue
            handler.detectors[det_name] = detector_model

        # build controllers
        for (ctrl_name, ctrl_info), ctrl_class in zip(
            self.config.controllers.items(), self.controllers
        ):
            controller = Factory.build_controller(
                name=ctrl_name,
                ctrl_info=ctrl_info,
                ctrl_class=ctrl_class,
                handler=handler,
                virtual_bus=self.virtual_bus,
                module_bus=self.module_bus,
            )
            self.controllers[ctrl_name] = controller

        # register signals...
        for ctrl in self.controllers.values():
            ctrl.registration_phase()

    def connect_to_virtual(self) -> None:
        """Connect the controller to the virtual layer."""
        for ctrl in self.controllers.values():
            ctrl.connection_phase()
