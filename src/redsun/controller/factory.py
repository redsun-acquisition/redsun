"""
The ``factory`` module contains all the tooling necessary for the dynamic building of internal components of RedSun.

RedSun operates by dynamically loading external plugins with different archetypes
(single or multiple controllers, single or multiple models, combination of controllers and models, etc.)
to create a unique running instance.

This mechanism allows for selecting an engine different from the default Bluesky ``RunEngine``;
but the new engine should still implement the same public API.

This module operates within the RedSun core code and is not exposed to the toolkit or the user.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Type, Union

from sunflare.config import AcquisitionEngineTypes
from sunflare.log import get_logger

if TYPE_CHECKING:
    import logging

    from sunflare.config import ControllerInfo, DetectorModelInfo, MotorModelInfo
    from sunflare.controller import BaseController
    from sunflare.engine import EngineHandler
    from sunflare.engine.detector import DetectorProtocol
    from sunflare.engine.motor import MotorProtocol
    from sunflare.virtualbus import ModuleVirtualBus

    from redsun.virtual import HardwareVirtualBus

__all__ = ["Factory"]


class Factory:
    """Factory base class."""

    _logger: logging.Logger = get_logger()

    @classmethod
    def build_handler(
        cls,
        engine: AcquisitionEngineTypes,
        virtual_bus: HardwareVirtualBus,
        module_bus: ModuleVirtualBus,
    ) -> EngineHandler:
        """Build the handler.

        Parameters
        ----------
        engine: ``AcquisitionEngineTypes``
            Selected acquisition engine.
        virtual_bus: ``HardwareVirtualBus``
            Hardware control virtual bus.
        module_bus: ``ModuleVirtualBus``
            Module virtual bus.

        Returns
        -------
        ``EngineHandler``
            The built handler. Specific type depends on the selected engine.

        Raises
        ------
        RuntimeError
            If the selected engine is not supported or if the handler could not be built.
        """
        if engine == AcquisitionEngineTypes.BLUESKY:
            try:
                from redsun.engine.bluesky import BlueskyHandler

                return BlueskyHandler(virtual_bus, module_bus)
            except Exception as e:
                raise RuntimeError(f"Failed to build handler for engine {engine}: {e}")
        else:
            raise RuntimeError(f"Unsupported engine: {engine}")

    @classmethod
    def build_model(
        cls,
        name: str,
        model_class: Union[
            Type[MotorProtocol[MotorModelInfo]],
            Type[DetectorProtocol[DetectorModelInfo]],
        ],
        model_info: MotorModelInfo | DetectorModelInfo,
    ) -> Optional[
        Union[MotorProtocol[MotorModelInfo], DetectorProtocol[DetectorModelInfo]]
    ]:
        """Build the model.

        Parameters
        ----------
        name: ``str``
            The name of the model.
        model_class: ``Union[Type[MotorProtocol[MotorModelInfo]], Type[DetectorProtocol[DetectorModelInfo]]]``
            The class of the model.
        model_info: ``Union[MotorModelInfo, DetectorModelInfo]``
            The model information.

        Returns
        -------
        ``Optional[Union[MotorProtocol[MotorModelInfo], DetectorProtocol[DetectorModelInfo]]]``
            The built model. ``None`` if the model could not be built.
        """
        try:
            return model_class(name, model_info)
        except Exception as e:
            cls._logger.exception(f"Failed to build model {name}: {e}")
            return None

    @classmethod
    def build_controller(
        cls,
        name: str,
        ctrl_info: ControllerInfo,
        ctrl_class: Type[BaseController],
        handler: EngineHandler,
        virtual_bus: HardwareVirtualBus,
        module_bus: ModuleVirtualBus,
    ) -> Optional[BaseController]:
        """Build the controller.

        Parameters
        ----------
        name: ``str``
            The name of the controller.
        ctrl_info: ``ControllerInfo``
            The controller information.
        ctrl_class: ``Type[BaseController]``
            The class of the controller.
        handler: ``EngineHandler``
            The handler.
        virtual_bus: ``HardwareVirtualBus``
            Hardware control virtual bus.
        module_bus: ``ModuleVirtualBus``
            Module virtual bus.

        Returns
        -------
        ``Optional[BaseController]``
            The built controller. ``None`` if the controller could not be built.

        Notes
        -----
        The ``name`` parameter is currently not used.
        """
        try:
            return ctrl_class(ctrl_info, handler, virtual_bus, module_bus)
        except Exception as e:
            cls._logger.exception(f"Failed to build controller {name}: {e}")
            return None
