"""Redsun main hardware controller module."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sunflare.log import Loggable

from redsun.controller.factory import Factory

if TYPE_CHECKING:
    from sunflare.config import RedSunInstanceInfo
    from sunflare.controller import BaseController
    from sunflare.virtualbus import ModuleVirtualBus

    from redsun.common import Backend
    from redsun.virtual import HardwareVirtualBus


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
    classes : Backend
        Dictionary of factory classes for devices and controllers.
    """

    def __init__(
        self,
        config: RedSunInstanceInfo,
        virtual_bus: HardwareVirtualBus,
        module_bus: ModuleVirtualBus,
        classes: Backend,
    ):
        self.config = config
        self.virtual_bus = virtual_bus
        self.module_bus = module_bus
        self.classes = classes
        self.controllers: dict[str, BaseController] = {}

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
        handler = Factory.build_handler(self.config, self.virtual_bus, self.module_bus)

        motors_info = self.config.motors
        detectors_info = self.config.detectors
        controllers_info = self.config.controllers

        # build motors
        for motor_name, motor_info in motors_info.items():
            motor_class = self.classes["motors"][motor_name]
            motor_obj = Factory.build_motor(
                name=motor_name,
                motor_class=motor_class,
                motor_info=motor_info,
            )
            if motor_obj is None:
                continue
            handler.motors[motor_name] = motor_obj

        # build detectors
        for det_name, det_info in detectors_info.items():
            detector_class = self.classes["detectors"][det_name]
            detector_model = Factory.build_detector(
                name=det_name, detector_class=detector_class, detector_info=det_info
            )
            if detector_model is None:
                continue
            handler.detectors[det_name] = detector_model

        # build controllers
        for ctrl_name, ctrl_info in controllers_info.items():
            ctrl_class = self.classes["controllers"][ctrl_name]
            controller = Factory.build_controller(
                name=ctrl_name,
                ctrl_info=ctrl_info,
                ctrl_class=ctrl_class,
                handler=handler,
                virtual_bus=self.virtual_bus,
                module_bus=self.module_bus,
            )
            if controller is None:
                continue
            self.controllers[ctrl_name] = controller

        # register signals...
        for ctrl in self.controllers.values():
            ctrl.registration_phase()

    def connect_to_virtual(self) -> None:
        """Connect the controller to the virtual layer."""
        for ctrl in self.controllers.values():
            ctrl.connection_phase()
