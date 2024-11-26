# noqa: D104

from typing import TYPE_CHECKING, final

from redsun.controller.factory import create_engine
from sunflare.log import Loggable

if TYPE_CHECKING:
    from typing import Optional

    from sunflare.config import RedSunInstanceInfo
    from sunflare.engine import EngineHandler
    from sunflare.virtualbus import VirtualBus

__all__ = ["RedSunHardwareController"]


@final
class RedSunHardwareController(Loggable):
    """Main hardware controller."""

    _instance: "Optional[RedSunHardwareController]" = None

    def __new__(cls) -> "RedSunHardwareController":  # noqa: D102
        # singleton pattern
        if cls._instance is None:
            cls._instance = object.__new__(cls)
        return cls._instance

    def __init__(
        self,
        instance_info: "RedSunInstanceInfo",
        virtual_bus: "VirtualBus",
        module_bus: "VirtualBus",
    ) -> None:
        self.__virtual_bus = virtual_bus
        self.__module_bus = module_bus
        self.__handler = create_engine(instance_info, virtual_bus, module_bus)
        self.info("{0} initialized.".format(self.handler.__class__.__name__))

    @property
    def virtual_bus(self) -> "VirtualBus":
        """Inter-module virtual bus."""
        return self.__virtual_bus

    @property
    def module_bus(self) -> "VirtualBus":
        """Inter-module virtual bus."""
        return self.__module_bus

    @property
    def handler(self) -> "EngineHandler":
        """
        Acquisition engine handler.

        The specific handler class is determined by the configuration.
        """
        return self.__handler
