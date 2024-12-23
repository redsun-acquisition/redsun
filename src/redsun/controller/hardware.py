"""Redsun main hardware controller module."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from sunflare.log import Loggable

from redsun.controller.factory import ControllerFactory, HandlerFactory, ModelFactory

if TYPE_CHECKING:
    from typing import Tuple, Type

    from sunflare.config import ControllerInfo, DetectorModelInfo, MotorModelInfo
    from sunflare.controller import BaseController
    from sunflare.engine.detector import DetectorProtocol
    from sunflare.engine.motor import MotorProtocol
    from sunflare.virtualbus import ModuleVirtualBus

    from redsun.common.types import RedSunConfigInfo, Registry
    from redsun.engine.bluesky import BlueskyHandler
    from redsun.virtual import HardwareVirtualBus


class RedsunMainHardwareController(Loggable):
    """Redsun main hardware controller.

    The main controller builds all the hardware controllers that are listed in the configuration.

    It keeps hold of the following references:

    - the device registry;
    - the engine handler;
    - the built controllers.

    Parameters
    ----------
    engine : AcquisitionEngineTypes
        Selected acquisition engine.
    virtual_bus : HardwareVirtualBus
        Hardware virtual bus.
    module_bus : ModuleVirtualBus
        Module virtual bus.
    """

    def __init__(
        self,
        config: RedSunConfigInfo,
        virtual_bus: HardwareVirtualBus,
        module_bus: ModuleVirtualBus,
    ) -> None:
        self._config = config
        self._virtual_bus = virtual_bus
        self._module_bus = module_bus

        self._controllers: dict[str, BaseController]
        self._handler: BlueskyHandler

        self._engine_factory = HandlerFactory(config["engine"], virtual_bus, module_bus)
        self._model_factory = ModelFactory(config)
        self._controller_factory = ControllerFactory(config, virtual_bus, module_bus)

    @property
    def virtual_bus(self) -> HardwareVirtualBus:
        """Hardware virtual bus."""
        return self._virtual_bus

    @property
    def module_bus(self) -> ModuleVirtualBus:
        """Module virtual bus."""
        return self._module_bus

    @property
    def controllers(self) -> dict[str, BaseController]:
        """The built controllers."""
        return self._controllers

    @property
    def handler(self) -> BlueskyHandler:
        """The engine handler."""
        return self._handler

    def build_layer(self, registry: Registry) -> None:
        """Build the controller layer.

        The method builds the full controller layer in a bottom-up fashion:

        - build the device models;
        - build the engine handler;
        - build the controllers;
        - build the storage backend (currently not implemented).

        After all objects are build, the registration phase occurs and all signals that are intended to be
        exposed to the virtual buses are registered accordingly to the hardware or module virtual bus.

        During the building of the models and controllers, an error may occur if the configuration
        file is not correct. The error caused by the creation of that specific object is logged,
        the creation is skipped, and the process continues with the next object.

        Parameters
        ----------
        registry : Registry
            Device registry loaded at startup.
        """
        # build engine handler
        # TODO: add a try-except block to catch
        #       any exception thrown during the initialization
        self._handler = self._engine_factory.build()

        # build motors
        motors = cast(
            list[Tuple[str, Type[MotorModelInfo], Type[MotorProtocol[MotorModelInfo]]]],
            registry.get("motors", []),
        )
        motors_params = self._config.get("motors", {})
        for motor in motors:
            motor_name, motor_info_cls, motor_model_cls = motor
            # TODO: the "Optional" type for models and controllers causes a mypy error;
            #       decide whether to keep it as it is or not
            params = motors_params.get(motor_name, {})  # type: ignore[union-attr]

            # TODO: add a try-except block to catch
            #       any exception thrown during the initialization
            motor_model = self._model_factory.build_motor(
                name=motor_name,
                info_dict=params,
                model_info_cls=motor_info_cls,
                model_cls=motor_model_cls,
            )
            self._handler.motors[motor_name] = motor_model

        # build detectors
        detectors = cast(
            list[
                Tuple[
                    str,
                    Type[DetectorModelInfo],
                    Type[DetectorProtocol[DetectorModelInfo]],
                ]
            ],
            registry.get("detectors", []),
        )
        detectors_params = self._config.get("detectors", {})
        for detector in detectors:
            det_name, det_info_cls, det_model_cls = detector
            # TODO: the "Optional" type for models and controllers causes a mypy error;
            #       decide whether to keep it as it is or not
            params = detectors_params.get(det_name, {})  # type: ignore[union-attr]

            # TODO: add a try-except block to catch
            #       any exception thrown during the initialization
            detector_model = self._model_factory.build_detector(
                name=det_name,
                info_dict=params,
                model_info_cls=det_info_cls,
                model_cls=det_model_cls,
            )
            self._handler.detectors[det_name] = detector_model

        # build controllers
        controllers = cast(
            list[
                Tuple[
                    str,
                    Type[ControllerInfo],
                    Type[BaseController],
                ]
            ],
            registry.get("controllers", []),
        )
        controllers_params = self._config.get("controllers", {})
        for controller_tuple in controllers:
            ctrl_name, ctrl_info_cls, ctrl_cls = controller_tuple
            params = controllers_params.get(ctrl_name, {})  # type: ignore[union-attr]

            controller = self._controller_factory.build(
                ctrl_name, params, self._handler, ctrl_info_cls, ctrl_cls
            )
            self._controllers[ctrl_name] = controller

        # register signals
        for ctrl in self._controllers.values():
            ctrl.registration_phase()


def build_controller_layer(
    config: RedSunConfigInfo,
    registry: Registry,
    virtual_bus: HardwareVirtualBus,
    module_bus: ModuleVirtualBus,
) -> RedsunMainHardwareController:
    """Build the controller layer.

    Parameters
    ----------
    config : RedSunConfigInfo
        RedSun configuration.
    registry : Registry
        Registry containing the loaded plugins classes.
        - keys: group names (i.e. "motors", "detectors", "controllers")
        - values: list of tuples containing:
            - device name
            - model info class
            - model class
    """
    layer = RedsunMainHardwareController(config, virtual_bus, module_bus)
    layer.build_layer(registry)
    return layer
