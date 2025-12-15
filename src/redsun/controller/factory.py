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

from sunflare.model import PModel
from sunflare.presenter import PPresenter

if TYPE_CHECKING:
    from typing import Protocol

    from sunflare.config import PModelInfo, PPresenterInfo
    from sunflare.model import PModel
    from sunflare.presenter import PPresenter
    from sunflare.virtual import VirtualBus

    class BuildableModel(PModel, Protocol):  # noqa: D101
        def __init__(self, name: str, model_info: PModelInfo) -> None: ...

    class BuildablePresenter(PPresenter, Protocol):  # noqa: D101
        def __init__(
            self,
            ctrl_info: PPresenterInfo,
            models: Mapping[str, PModel],
            virtual_bus: VirtualBus,
        ) -> None: ...


__all__ = ["BackendFactory"]


class BackendFactory:
    """Internal factory  class."""

    _logger: ClassVar[logging.Logger] = logging.getLogger("redsun")

    @classmethod
    def build_model(
        cls,
        name: str,
        model_class: type[BuildableModel],
        model_info: PModelInfo,
    ) -> Optional[PModel]:
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
        ctrl_info: PPresenterInfo,
        ctrl_class: type[BuildablePresenter],
        models: Mapping[str, PModel],
        virtual_bus: VirtualBus,
    ) -> Optional[PPresenter]:
        """Build the controller.

        Parameters
        ----------
        name: ``str``
            Controller name. Used for logging purposes.
        ctrl_info: ``PresenterInfo``
            Controller information container.
        ctrl_class: ``type[BaseController]``
            Controller class.
        models: ``Mapping[str, PModel]``
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
