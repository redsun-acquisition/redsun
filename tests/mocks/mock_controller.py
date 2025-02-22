from attrs import define

from sunflare.config import ControllerInfo
from sunflare.controller import ControllerProtocol
from sunflare.model import ModelProtocol
from sunflare.virtual import VirtualBus

@define(kw_only=True)
class MockControllerInfo(ControllerInfo):
    """Mock controller information model."""
    string: str
    integer: int
    floating: float
    boolean: bool


class MockController(ControllerProtocol):

    _ctrl_info: MockControllerInfo

    def __init__(self, 
                ctrl_info: MockControllerInfo, 
                models: dict[str, ModelProtocol],
                virtual_bus: VirtualBus):
        self._ctrl_info = ctrl_info
        self._models = models
        self._virtual_bus = virtual_bus

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

class NonDerivedController:

    def __init__(self, 
                ctrl_info: MockControllerInfo, 
                models: dict[str, ModelProtocol],
                virtual_bus: VirtualBus):
            ...
        
    def shutdown(self) -> None:
        ...

    def registration_phase(self) -> None:
        ...

    def connection_phase(self) -> None:
        ...
