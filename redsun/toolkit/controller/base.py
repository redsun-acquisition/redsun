from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
from redsun.toolkit.config import ControllerInfo
from redsun.toolkit.engine import DeviceRegistry
from redsun.toolkit.utils import create_evented_dataclass
from redsun.toolkit.virtualbus import VirtualBus
from redsun.toolkit.log import Loggable
if TYPE_CHECKING:
    from typing import Any
    from redsun.toolkit.virtualbus import VirtualBus
    from redsun.toolkit.config import ControllerInfo
    from redsun.toolkit.engine import DeviceRegistry

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
    """

    @abstractmethod
    def __init__(self, 
                 ctrl_info: ControllerInfo, 
                 dev_registry: DeviceRegistry, 
                 virtual_bus: VirtualBus, 
                 module_bus: VirtualBus) -> None:
        super().__init__(ctrl_info, dev_registry, virtual_bus, module_bus)
    