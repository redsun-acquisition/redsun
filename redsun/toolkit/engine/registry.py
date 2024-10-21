from typing import TYPE_CHECKING
from abc import ABC, abstractmethod
from redsun.toolkit.log import Loggable

if TYPE_CHECKING:
    from redsun.toolkit.virtualbus import VirtualBus
    from redsun.toolkit.config import RedSunInstanceInfo
    from typing import Any, Dict

__all__ = ['DeviceRegistry']

class DeviceRegistry(ABC, Loggable):
    """ `DeviceRegistry` abstract base class. Implements `Loggable` protocol.
    
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
    
    Attributes
    ----------
    config : RedSunInstanceInfo
        RedSun instance configuration dataclass.
    virtual_bus : VirtualBus
        Module-local virtual bus.
    module_bus : VirtualBus
        Inter-module virtual bus.
    
    Properties
    ----------
    detectors : Dict[str, Any]
        Detectors dictionary. Device class type is engine-specific and must inherit from `DetectorModel`.
    Motors : Dict[str, Any]
        Motors dictionary. Device class type is engine-specific and must inherit from `MotorModel`.
    Lights : Dict[str, Any]
        Lights dictionary. Device class type is engine-specific and must inherit from `LightModel`.
    Scanners : Dict[str, Any]
        Scanners dictionary. Device class type is engine-specific and must inherit from `ScannerModel`.
    """

    @abstractmethod
    def __init__(self, config_options: "RedSunInstanceInfo", virtual_bus: "VirtualBus", module_bus: "VirtualBus"):
        self.config = config_options
        self.virtual_bus = virtual_bus
        self.module_bus = module_bus
    
    @abstractmethod
    def register_device(name: str, device: "Any") -> None:
        """ Add a new device to the registry. 
        
        Child classes must implement this method to add a new device to the registry.

        Parameters
        ----------
        name : str
            Device unique identifier.
        device : Any
            Device instance \\
            The device instance must be coherent with the selected acquisition engine.\\
            This means that devices to be added to the registry must inherit from the correct device model class for the selected engine.
        """
        ...
    
    @abstractmethod
    @property
    def detectors(self) -> "Dict[str, Any]":
        ...

    @abstractmethod
    @property
    def motors(self) -> "Dict[str, Any]":
        ...
    
    @abstractmethod
    @property
    def lights(self) -> "Dict[str, Any]":
        ...
    
    @abstractmethod
    @property
    def scanners(self) -> "Dict[str, Any]":
        ...