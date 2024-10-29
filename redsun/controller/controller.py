from typing import TYPE_CHECKING
from redsun.toolkit.log import Loggable
from redsun.controller.factory import create_engine
if TYPE_CHECKING:
    from redsun.toolkit.config import RedSunInstanceInfo
    from redsun.toolkit.virtualbus import VirtualBus

class RedSunHardwareController(Loggable):
    """ Main hardware controller.
    """
    def __init__(self, 
                 instance_info: "RedSunInstanceInfo",
                 virtual_bus: "VirtualBus",
                 module_bus: "VirtualBus") -> None:
        self.virtual_bus = virtual_bus
        self.module_bus = module_bus
        self.handler = create_engine(instance_info.engine)(instance_info, virtual_bus, module_bus)
        self.info("{0} initialized.".format(self.handler.__class__.__name__))
    
    def add_plugin(self) -> None:
        """ Add a new plugin to the currently running application.
        """
        ...
