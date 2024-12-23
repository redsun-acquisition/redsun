"""
The ``factory`` module contains all the tooling necessary for the dynamic building of internal components of RedSun.

RedSun operates by dynamically loading external plugins with different archetypes
(single or multiple controllers, single or multiple models, combination of controllers and models, etc.)
to create a unique running instance.

Each factory selects the correct type of object to build based on the ``engine`` field of the configuration file.

This mechanism allows for selecting an engine different from the default Bluesky ``RunEngine``;
but the new engine should still implement the same public API.

This module operates within the RedSun core code and is not exposed to the toolkit or the user.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Type, cast

from sunflare.config import AcquisitionEngineTypes
from sunflare.controller import BaseController
from sunflare.engine import EngineHandler
from sunflare.virtualbus import ModuleVirtualBus

from redsun.common.types import RedSunConfigInfo
from redsun.engine.bluesky import BlueskyHandler
from redsun.virtual import HardwareVirtualBus

if TYPE_CHECKING:
    from sunflare.config import ControllerInfo, DetectorModelInfo, MotorModelInfo
    from sunflare.engine.detector import DetectorProtocol
    from sunflare.engine.motor import MotorProtocol

__all__ = ["HandlerFactory", "ControllerFactory"]


class HandlerFactory:
    """Engine handler factory.

    Parameters
    ----------
    engine : AcquisitionEngineTypes
        Selected acquisition engine.
    virtual_bus : HardwareVirtualBus
        Hardware control virtual bus.
    module_bus : ModuleVirtualBus
        Module virtual bus.
    """

    def __init__(
        self,
        engine: AcquisitionEngineTypes,
        virtual_bus: HardwareVirtualBus,
        module_bus: ModuleVirtualBus,
    ) -> None:
        self._virtual_bus = virtual_bus
        self._module_bus = module_bus
        self.__handler_factory: Type[EngineHandler]

        if engine == AcquisitionEngineTypes.BLUESKY:
            self.__handler_factory = BlueskyHandler
        else:
            raise ValueError(f"Invalid engine: {engine}")

    def build(self) -> BlueskyHandler:
        """Build the handler."""
        factory = cast(Type[BlueskyHandler], self.__handler_factory)
        return factory(self._virtual_bus, self._module_bus)


# TODO: a single factory model method should be enough
class ModelFactory:
    """Model factory.

    This factory is responsible to build the model information objects related
    to each hardware model.

    Models are separated from interactions with the virtual buses, which passes
    through the hardware controllers; hence they don't need to be aware of the buses.

    Parameters
    ----------
    config : RedSunConfigInfo
        Configuration dictionary.
    """

    def __init__(self, config: RedSunConfigInfo) -> None:
        self._config = config

    def build_motor(
        self,
        name: str,
        info_dict: dict[str, Any],
        model_info_cls: Type[MotorModelInfo],
        model_cls: Type[MotorProtocol[MotorModelInfo]],
    ) -> MotorProtocol[MotorModelInfo]:
        """Build the motor model.

        Before building the model, the factory should build the model information. This will provide
        the necessary validation checks and ensure that the model is coherent.

        Parameters
        ----------
        name : str
            Model name.
        model_info : ModelInfoTypes
            Model information.
        """
        # TODO: building the model info object
        #       should be wrapped in a try-except block
        #       to catch any exception thrown by pydantic
        model_info_obj = model_info_cls(**info_dict)

        # TODO: building the model object
        #       should be wrapped in a try-except block
        #       to catch any exception thrown during the initialization
        #       of the model object
        model_obj = model_cls(name, model_info_obj)
        return model_obj

    def build_detector(
        self,
        name: str,
        info_dict: dict[str, Any],
        model_info_cls: Type[DetectorModelInfo],
        model_cls: Type[DetectorProtocol[DetectorModelInfo]],
    ) -> DetectorProtocol[DetectorModelInfo]:
        """Build the detector model.

        Before building the model, the factory should build the model information. This will provide
        the necessary validation checks and ensure that the model is coherent.

        Parameters
        ----------
        name : str
            Model name.
        info_dict : dict[str, Any]
            Model information extracted from the main configuration.
        model_info_cls : Type[DetectorModelInfo]
            Model-specific information class.
        model_cls : Type[DetectorModel]
            Model-specific class.

        Returns
        -------
        DetectorModel
            The built detector model.
        """
        # TODO: building the model info object
        #       should be wrapped in a try-except block
        #       to catch any exception thrown by pydantic
        model_info_obj = model_info_cls(**info_dict)

        # TODO: building the model object
        #       should be wrapped in a try-except block
        #       to catch any exception thrown during the initialization
        #       of the model object
        model_obj = model_cls(name, model_info_obj)
        return model_obj


class ControllerFactory:
    """Controller factory.

    Parameters
    ----------
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

    def build(
        self,
        name: str,  # TODO: use "name" parameter to distinguish controllers
        info_dict: dict[str, Any],
        handler: BlueskyHandler,
        ctrl_info_cls: Type[ControllerInfo],
        ctrl_cls: Type[BaseController],
    ) -> BaseController:
        """Build the controller.

        Parameters
        ----------
        name : str
            Controller name. Currently not used.
        info_dict : dict[str, Any]
            Controller information extracted from the main configuration.
        ctrl_info_cls : Type[ControllerInfo]
            Controller information class.
        """
        # TODO: building the controller info object
        #       should be wrapped in a try-except block
        #       to catch any exception thrown by pydantic
        ctrl_info_obj = ctrl_info_cls(**info_dict)

        # TODO: building the controller object
        #       should be wrapped in a try-except block
        #       to catch any exception thrown during the initialization
        #       of the model object
        # TODO: registry_obj causes a type error due to the fact that
        #       the controller class is specific to each engine;
        #       this is a problem rooted in the different engine design
        #       and should be addressed in the future
        ctrl_obj = ctrl_cls(
            ctrl_info_obj,
            handler,
            self._virtual_bus,
            self._module_bus,
        )
        return ctrl_obj
