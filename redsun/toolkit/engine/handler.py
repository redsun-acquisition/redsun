from typing import TYPE_CHECKING
from abc import ABC, abstractmethod
from redsun.toolkit.log import Loggable

if TYPE_CHECKING:
    from typing import Generator, Iterable, Union
    from redsun.toolkit.virtualbus import VirtualBus
    from redsun.toolkit.config import RedSunInstanceInfo
    from typing import Any, Dict

__all__ = ['EngineHandler']

class EngineHandler(ABC, Loggable):
    """ `EngineHandler` abstract base class. Implements `Loggable` protocol.
    
    The `EngineHandler` class is a singleton that stores all the devices currently
    deployed within a RedSun hardware module. It provides access to the rest of the controller layer
    to information for each device, allowing for execution of atomic operations such as moving
    a motor or setting a light intensity.

    At startup, the `EngineHandler` is populated with the devices defined in the configuration file. These
    can be then accessed as read-only dictionaries, indexing the device by unique identifiers.

    Each engine has its own dedicated `EngineHandler` instance, with common methods that are specialized
    for the specific engine type by using inheritance.

    `EngineHandler` classes hold dictionaries that are used to group up devices by type and provide
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
    engine : Any
        Engine instance.
    detectors : Dict[str, Any]
        Detectors dictionary. Device class type is engine-specific and must inherit from `DetectorModel`.
    motors : Dict[str, Any]
        Motors dictionary. Device class type is engine-specific and must inherit from `MotorModel`.
    lights : Dict[str, Any]
        Lights dictionary. Device class type is engine-specific and must inherit from `LightModel`.
    scanners : Dict[str, Any]
        Scanners dictionary. Device class type is engine-specific and must inherit from `ScannerModel`.
    workflows : Dict[str, Union[Generator, Iterable]]
        Workflows dictionary.
    """
    _workflows : Dict[str, "Union[Generator, Iterable]"] = {}

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
    def shutdown(self) -> None:
        """ Perform a clean shutdown of the engine and all its devices.
        """
        ...
    
    def register_workflow(self, name: str, workflow: "Union[Generator, Iterable]") -> None:
        """ Registers a new workflow in the handler.
        
        Parameters
        ----------
        name : str
            Workflow unique identifier.
        workflow : Union[Generator, Iterable]
            Workflow to be registered.
        """
        if type(workflow) not in (Generator, Iterable):
            self.error(f"\"{name}\" workflow must be either a Generator or an Iterable. Skipping registration.")
            return
        self._workflows[name] = workflow
    
    @abstractmethod
    @property
    def engine(self) -> "Any":
        """ Returns the engine instance.

        The return type is determined by the specific engine implementation.
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
    
    @property
    def workflows(self) -> "Dict[str, Union[Generator, Iterable]]":
        return self._workflows