"""Bluesky handler class."""

from typing import TYPE_CHECKING

from bluesky import RunEngine
from sunflare.engine import DetectorModel, EngineHandler, MotorModel
from sunflare.errors import UnsupportedDeviceType

if TYPE_CHECKING:
    from typing import Any, Dict

    from sunflare.config import RedSunInstanceInfo
    from sunflare.engine.bluesky import BlueskyDetectorModel, BlueskyMotorModel
    from sunflare.virtualbus import VirtualBus


class BlueskyHandler(EngineHandler):
    r"""
    ExEngine handler class.

    All models compatible with ExEngine are registered here at application startup.

    Parameters
    ----------
    config_options : RedSunInstanceInfo
        Configuration options for the RedSun instance.
    virtual_bus : VirtualBus
        The virtual bus instance for the RedSun instance.
    module_bus : VirtualBus
        The virtual bus instance for the module.
    """

    def __init__(
        self,
        config_options: "RedSunInstanceInfo",
        virtual_bus: "VirtualBus",
        module_bus: "VirtualBus",
    ) -> None:
        super().__init__(config_options, virtual_bus, module_bus)
