from typing import Mapping

from sunflare.presenter import Presenter
from sunflare.virtual import VirtualBus
from sunflare.device import PDevice

class MockController(Presenter):

    def __init__(
        self,
        devices: Mapping[str, PDevice],
        virtual_bus: VirtualBus,
        string: str,
        integer: int,
        floating: float,
        boolean: bool,
    ) -> None:
        super().__init__(devices, virtual_bus)
        self.string = string
        self.integer = integer
        self.floating = floating
        self.boolean = boolean


    def registration_phase(self) -> None:
        ...

    def connection_phase(self) -> None:
        ...

class BrokenController(Presenter):

    def __init__(
        self,
        devices: Mapping[str, PDevice],
        virtual_bus: VirtualBus,
        string: str,
        integer: int,
        floating: float,
        boolean: bool,
    ) -> None:
        raise Exception("Broken controller")

    def connect_to_virtual(self) -> None:
        ...

class NonDerivedController:

    def __init__(self, 
                devices: dict[str, PDevice],
                virtual_bus: VirtualBus,
                string: str,
                integer: int,
                floating: float,
                boolean: bool) -> None:
        self.devices = devices
        self.virtual_bus = virtual_bus
        self.string = string
        self.integer = integer
        self.floating = floating
        self.boolean = boolean

    def connect_to_virtual(self) -> None:
        ...
