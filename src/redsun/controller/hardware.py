"""Redsun main hardware controller module."""

from __future__ import annotations

from sunflare.log import Loggable

from typing import TYPE_CHECKING

from redsun.controller.factory import RegistryFactory, EngineFactory, ControllerFactory

if TYPE_CHECKING:
    from sunflare.config import RedSunInstanceInfo
    from sunflare.virtualbus import ModuleVirtualBus

    from redsun.controller.virtualbus import HardwareVirtualBus


class RedsunMainHardwareController(Loggable):
    """Redsun main hardware controller.

    The main controller builds all the hardware controllers that are listed in the configuration.

    Parameters
    ----------
    config : RedSunInstanceInfo
        RedSun instance configuration.
    virtual_bus : HardwareVirtualBus
        Hardware virtual bus.
    module_bus : ModuleVirtualBus
        Module virtual bus.
    """

    def __init__(
        self,
        config: RedSunInstanceInfo,
        virtual_bus: HardwareVirtualBus,
        module_bus: ModuleVirtualBus,
    ) -> None:
        self._config = config
        self._virtual_bus = virtual_bus
        self._module_bus = module_bus

        self._engine_factory = EngineFactory(config.engine, virtual_bus, module_bus)
        self._registry_factory = RegistryFactory(config.engine, virtual_bus, module_bus)
        self._controller_factory = ControllerFactory(
            config.engine, virtual_bus, module_bus
        )
