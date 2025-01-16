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

from typing import TYPE_CHECKING, Mapping, Optional

from sunflare.log import get_logger

if TYPE_CHECKING:
    import logging

    from sunflare.config import ControllerInfo, ModelInfo
    from sunflare.controller import ControllerProtocol
    from sunflare.model import ModelProtocol
    from sunflare.virtual import VirtualBus

__all__ = ["Factory"]


class Factory:
    """Factory base class."""

    _logger: logging.Logger = get_logger()

    @classmethod
    def build_model(
        cls,
        name: str,
        model_class: type[ModelProtocol],
        model_info: ModelInfo,
    ) -> Optional[ModelProtocol]:
        """Build the detector model.

        Parameters
        ----------
        name: ``str``
            The name of the detector.
        detector_class: ``type[DetectorProtocol[DetectorModelInfo]]``
            The class of the detector.
        detector_info: ``DetectorModelInfo``
            The detector information.

        Returns
        -------
        ``Optional[DetectorProtocol[DetectorModelInfo]]``
            The built detector model. ``None`` if the model could not be built.
        """
        try:
            return model_class(name, model_info)
        except Exception as e:
            cls._logger.exception(f"Failed to build detector {name}: {e}")
            return None

    @classmethod
    def build_controller(
        cls,
        name: str,
        ctrl_info: ControllerInfo,
        ctrl_class: type[ControllerProtocol],
        models: Mapping[str, ModelProtocol],
        virtual_bus: VirtualBus,
    ) -> Optional[ControllerProtocol]:
        """Build the controller.

        Parameters
        ----------
        name: ``str``
            The name of the controller.
        ctrl_info: ``ControllerInfo``
            Controller information container.
        ctrl_class: ``type[BaseController]``
            Controller class.
        models: ``Mapping[str, ModelProtocol]``
            Mapping of model names to model instances.
        virtual_bus: :class:`sunflare.virtual.VirtualBus`
            Hardware control virtual bus.

        Returns
        -------
        ``Optional[BaseController]``
            The built controller. ``None`` if the controller could not be built.

        Notes
        -----
        The ``name`` parameter is currently not used.
        """
        try:
            return ctrl_class(ctrl_info, models, virtual_bus)
        except Exception as e:
            cls._logger.exception(f"Failed to build controller {name}: {e}")
            return None
