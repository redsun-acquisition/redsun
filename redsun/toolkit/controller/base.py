from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
from redsun.toolkit.utils import create_evented_dataclass
if TYPE_CHECKING:
    from redsun.toolkit.virtualbus import VirtualBus
    from redsun.toolkit.config import ControllerInfo

class BaseController(ABC):
    """ Base controller class.

    Parameters
    ----------
    ctrl_info : ControllerInfo
        Controller information dataclass.
    virtual_bus : VirtualBus
        Intra-module virtual bus.
    module_bus : VirtualBus
        Inter-module virtual bus.
    """
    @abstractmethod
    def __init__(self, ctrl_info: "ControllerInfo", 
                virtual_bus: "VirtualBus", 
                module_bus: "VirtualBus") -> None:
        ...