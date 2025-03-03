from attrs import define

from typing import Mapping

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

    def __init__(
        self,
        ctrl_info: MockControllerInfo,
        models: Mapping[str, ModelProtocol],
        virtual_bus: VirtualBus,
    ) -> None:
        self.ctrl_info = ctrl_info
        self.models = models
        self.virtual_bus = virtual_bus

    def registration_phase(self) -> None:
        ...

    def connection_phase(self) -> None:
        ...

class NonDerivedControllerInfo:
    """Non-derived controller information model."""
    plugin_name: str
    plugin_id: str
    string: str
    integer: int
    floating: float
    boolean: bool

    def __init__(self, *, plugin_name: str, plugin_id: str, string: str, integer: int, floating: float, boolean: bool) -> None:
        self.plugin_name = plugin_name
        self.plugin_id = plugin_id
        self.string = string
        self.integer = integer
        self.floating = floating
        self.boolean = boolean

class NonDerivedController:

    def __init__(self, 
                ctrl_info: NonDerivedControllerInfo, 
                models: dict[str, ModelProtocol],
                virtual_bus: VirtualBus):
            ...
        
    def shutdown(self) -> None:
        ...

    def registration_phase(self) -> None:
        ...

    def connection_phase(self) -> None:
        ...
