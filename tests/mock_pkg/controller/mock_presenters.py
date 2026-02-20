from typing import Mapping

from sunflare.presenter import Presenter
from sunflare.device import PDevice


class MockController(Presenter):

    def __init__(
        self,
        name: str,
        devices: Mapping[str, PDevice],
        /,
        string: str = "",
        integer: int = 0,
        floating: float = 0.0,
        boolean: bool = False,
    ) -> None:
        super().__init__(name, devices)
        self.string = string
        self.integer = integer
        self.floating = floating
        self.boolean = boolean


class BrokenController(Presenter):

    def __init__(
        self,
        name: str,
        devices: Mapping[str, PDevice],
        /,
        string: str = "",
        integer: int = 0,
        floating: float = 0.0,
        boolean: bool = False,
    ) -> None:
        raise Exception("Broken controller")


class NonDerivedController:

    def __init__(
        self,
        name: str,
        devices: dict[str, PDevice],
        /,
        string: str = "",
        integer: int = 0,
        floating: float = 0.0,
        boolean: bool = False,
    ) -> None:
        self.name = name
        self.devices = devices
        self.string = string
        self.integer = integer
        self.floating = floating
        self.boolean = boolean
