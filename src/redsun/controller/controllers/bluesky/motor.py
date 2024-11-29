"""Stepper motor controller module."""

from typing import TYPE_CHECKING, TypeAlias

from sunflare.controller.bluesky import BlueskyController

from redsun.controller.controllers.motor import MotorControllerProtocol

if TYPE_CHECKING:
    from typing import Union

    from sunflare.config import ControllerInfo
    from sunflare.virtualbus import VirtualBus
    from sunflare.engine.bluesky.registry import BlueskyDeviceRegistry


PositionType: TypeAlias = "dict[str, Union[int, float, str]]"


class StepperController(BlueskyController, MotorControllerProtocol[PositionType]):
    """Stepper motor controller class."""

    def __init__(
        self,
        ctrl_info: "ControllerInfo",
        registry: "BlueskyDeviceRegistry",
        virtual_bus: "VirtualBus",
        module_bus: "VirtualBus",
    ) -> None:
        super().__init__(ctrl_info, registry, virtual_bus, module_bus)

    def move(self, motor: str, value: PositionType) -> None:
        """Move the stepper motor."""
        ...

    def location(self, motor: str) -> PositionType:
        """Get the stepper motor location."""
        return dict()

    def registration_phase(self) -> None:  # noqa: D102
        # inherited docstring
        ...

    def connection_phase(self) -> None:  # noqa: D102
        # inherited docstring
        ...

    def shutdown(self) -> None:  # noqa: D102
        # inherited docstring
        ...
