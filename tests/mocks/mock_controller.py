from typing import ClassVar

from sunflare.config import ControllerInfo
from sunflare.controller import BaseController
from sunflare.engine import EngineHandler
from sunflare.virtual import VirtualBus, ModuleVirtualBus
from psygnal import SignalGroupDescriptor

class MockControllerInfo(ControllerInfo):
    """Mock controller information model."""
    string: str
    integer: int
    floating: float
    boolean: bool
    events: ClassVar[SignalGroupDescriptor] = SignalGroupDescriptor()


class MockController(BaseController):

    _ctrl_info: MockControllerInfo

    def __init__(self, 
                ctrl_info: MockControllerInfo, 
                handler: EngineHandler, 
                virtual_bus: VirtualBus, 
                module_bus: ModuleVirtualBus):
        super().__init__(ctrl_info, handler, virtual_bus, module_bus)

    def shutdown(self) -> None:
        ...

    def registration_phase(self) -> None:
        ...

    def connection_phase(self) -> None:
        ...

class NonDerivedControllerInfo:
    """Non-derived controller information model."""
    string: str
    integer: int
    floating: float
    boolean: bool
    events: ClassVar[SignalGroupDescriptor] = SignalGroupDescriptor()

class NonDerivedController(BaseController):

    def __init__(self, 
                ctrl_info: MockControllerInfo, 
                handler: EngineHandler, 
                virtual_bus: VirtualBus, 
                module_bus: ModuleVirtualBus):
            ...
        
    def shutdown(self) -> None:
        ...

    def registration_phase(self) -> None:
        ...

    def connection_phase(self) -> None:
        ...
