from typing import TYPE_CHECKING
from abc import ABC, abstractmethod

if TYPE_CHECKING:
    from redsun.toolkit.virtualbus import VirtualBus
    from redsun.config import RedSunInstanceInfo

class DeviceRegistry(ABC):
    """ `DeviceRegistry` abstract base class.
    
    The `DeviceRegistry` class is a singleton that stores all the devices currently
    deployed within a RedSun hardware module. It provides access to the rest of the controller layer
    to information for each device, allowing for execution of atomic operations such as moving
    a motor or setting a light intensity.

    At startup, the `DeviceRegistry` is populated with the devices defined in the configuration file. These
    can be then accessed as read-only dictionaries, indexing the device by unique identifiers.

    Each engine has its own dedicated `DeviceRegistry` instance, with common methods that are specialized
    for the specific engine type by using inheritance.

    `DeviceRegistry` classes hold dictionaries that are used to group up devices by type and provide
    a key-value access to specific devices the user wants to interact with. The types of devices
    the registry can provide depend on the engine capabilities to support that type of device.

    Parameters
    ----------
    config_options: RedSunInstanceInfo
        RedSun instance configuration dataclass.

    virtual_bus : VirtualBus
        Module-local virtual bus.
    
    module_bus : VirtualBus
        Inter-module virtual bus.
    """

    def __init__(self, config_options: "RedSunInstanceInfo", virtual_bus: "VirtualBus", module_bus: "VirtualBus"):
        self._config = config_options
        self._virtual_bus = virtual_bus
        self._module_bus = module_bus