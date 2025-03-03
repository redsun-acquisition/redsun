"""
The ``factory`` module contains all the tooling necessary for the dynamic building of internal components of Redsun.

Redsun operates by dynamically loading external plugins with different archetypes
(single or multiple controllers, single or multiple models, combination of controllers and models, etc.)
to create a unique running instance.

This module operates within Redsun and is not exposed to the toolkit or the user.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, ClassVar, Mapping, Optional

if TYPE_CHECKING:
    from sunflare.config import ControllerInfoProtocol, ModelInfoProtocol
    from sunflare.controller import ControllerProtocol
    from sunflare.model import ModelProtocol
    from sunflare.virtual import VirtualBus

__all__ = ["BackendFactory"]


class BackendFactory:
    """Internal factory  class."""

    _logger: ClassVar[logging.Logger] = logging.getLogger("redsun")

    @classmethod
    def build_model(
        cls,
        name: str,
        model_class: type[ModelProtocol],
        model_info: ModelInfoProtocol,
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
            cls._logger.exception(f'Failed to build model "{name}": {e}')
            return None

    @classmethod
    def build_controller(
        cls,
        name: str,
        ctrl_info: ControllerInfoProtocol,
        ctrl_class: type[ControllerProtocol],
        models: Mapping[str, ModelProtocol],
        virtual_bus: VirtualBus,
    ) -> Optional[ControllerProtocol]:
        """Build the controller.

        Parameters
        ----------
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
        """
        try:
            return ctrl_class(ctrl_info, models, virtual_bus)
        except Exception as e:
            cls._logger.exception(f'Failed to build controller "{name}": {e}')
            return None
