from typing import TYPE_CHECKING
from redsun.engine.registry import DeviceRegistry

if TYPE_CHECKING:
    from redsun.config import RedSunInstanceInfo
    from redsun.toolkit.virtualbus import VirtualBus

class ExEngineRegistry(DeviceRegistry):
    """ ExEngine device registry class.

    All models compatible with ExEngine are registered here at application startup.
    """

    def __init__(self, config_options: RedSunInstanceInfo, virtual_bus: VirtualBus, module_bus: VirtualBus):
        super().__init__(config_options, virtual_bus, module_bus)