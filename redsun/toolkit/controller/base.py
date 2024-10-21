from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
from redsun.toolkit.config import ControllerInfo
from redsun.toolkit.engine import DeviceRegistry
from redsun.toolkit.utils import create_evented_dataclass
from redsun.toolkit.virtualbus import VirtualBus
from redsun.toolkit.log import Loggable
if TYPE_CHECKING:
    from typing import Any, Iterable, Generator, Union
    from redsun.toolkit.virtualbus import VirtualBus
    from redsun.toolkit.config import ControllerInfo
    from redsun.toolkit.engine import DeviceRegistry

__all__ = ['DeviceController', 'ComputationalController']

class BaseController(ABC, Loggable):
    """ Base controller class. Implements `Loggable` protocol.

    Parameters
    ----------
    ctrl_info : ControllerInfo
        Controller information dataclass.
    dev_registry : DeviceRegistry
        Device registry API.
    virtual_bus : VirtualBus
        Intra-module virtual bus.
    module_bus : VirtualBus
        Inter-module virtual bus.
    """
    @abstractmethod
    def __init__(self, 
                ctrl_info: "ControllerInfo",
                dev_registry: "DeviceRegistry",
                virtual_bus: "VirtualBus", 
                module_bus: "VirtualBus") -> None:
        self._dev_registry = dev_registry
        self._virtual_bus = virtual_bus
        self._module_bus = module_bus
        FullModelInfo = create_evented_dataclass(ctrl_info.controllerName + "Info", type(ctrl_info))
        self._modelInfo = FullModelInfo(**ctrl_info.controllerParams)

    @property
    def controllerName(self) -> str:
        return self._modelInfo.controllerName

    @property
    def supportedEngines(self) -> list[str]:
        return self._modelInfo.supportedEngines

    @property
    def controllerParams(self) -> "dict[str, Any]":
        return self._modelInfo.controllerParams

class DeviceController(BaseController):
    """ Device controller base class.

    Parameters
    ----------
    ctrl_info : ControllerInfo
        Controller information dataclass.
    dev_registry : DeviceRegistry
        Device registry API.
    virtual_bus : VirtualBus
        Intra-module virtual bus.
    module_bus : VirtualBus
        Inter-module virtual bus.
    """

    @abstractmethod
    def __init__(self, 
                 ctrl_info: ControllerInfo, 
                 dev_registry: DeviceRegistry, 
                 virtual_bus: VirtualBus, 
                 module_bus: VirtualBus) -> None:
        super().__init__(ctrl_info, dev_registry, virtual_bus, module_bus)
    
    # TODO: add APIs...

class ComputationalController(BaseController):
    """ Computational controller base class.

    Parameters
    ----------
    ctrl_info : ControllerInfo
        Controller information dataclass.
    dev_registry : DeviceRegistry
        Device registry API.
    virtual_bus : VirtualBus
        Intra-module virtual bus.
    module_bus : VirtualBus
        Inter-module virtual bus.
    """

    @abstractmethod
    def __init__(self, 
                 ctrl_info: ControllerInfo, 
                 dev_registry: DeviceRegistry, 
                 virtual_bus: VirtualBus, 
                 module_bus: VirtualBus) -> None:
        super().__init__(ctrl_info, dev_registry, virtual_bus, module_bus)
    
    @abstractmethod
    def register_workflow(self, workflow: "Union[Iterable, Generator]") -> None:
        """ Submits a new available workflow.

        A workflow can be a generator or an iterable object constructed within the controller.

        Parameters
        ----------
        workflow : Union[Iterable, Generator]
            Workflow generator or iterable.
        """
        ...
    