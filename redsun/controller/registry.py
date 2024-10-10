from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redsun.toolkit.virtualbus import VirtualBus
    from redsun.config import RedSunInstanceInfo

class DeviceRegistry:
    """ The `DeviceRegistry` class is a singleton that stores all the devices currently
    deployed within a RedSun hardware module. It provides access to the rest of the controller layer
    to information for each device, allowing for execution of atomic operations such as moving
    a motor or setting a light intensity.

    At startup, the `DeviceRegistry` is populated with the devices defined in the configuration file. These
    can be then accessed as read-only dictionaries, indexing the device by unique identifiers.

    Parameters
    ----------
    config_options: `RedSunInstanceInfo`
        RedSun instance configuration dataclass.

    virtual_bus : `VirtualBus`
        Module-local virtual bus.
    
    module_bus : `VirtualBus`
        Inter-module virtual bus.
    """
    def __init__(self, config_options: "RedSunInstanceInfo", virtual_bus: "VirtualBus", module_bus: "VirtualBus"):
        self._config = config_options
        self._virtual_bus = virtual_bus
        self._module_bus = module_bus

