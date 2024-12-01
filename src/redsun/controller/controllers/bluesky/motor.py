"""Bluesky motor controller module."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeAlias

from sunflare.controller.bluesky import BlueskyController

from redsun.controller.controllers.motor import MotorControllerProtocol

if TYPE_CHECKING:
    from typing import Union

    from sunflare.types import AxisLocation
    from sunflare.config import ControllerInfo
    from sunflare.virtualbus import VirtualBus
    from sunflare.engine.bluesky.registry import BlueskyDeviceRegistry

TA: TypeAlias = Union[int, float, str]


class MotorController(BlueskyController, MotorControllerProtocol):
    """Motor controller class."""

    def __init__(
        self,
        ctrl_info: ControllerInfo,
        registry: BlueskyDeviceRegistry,
        virtual_bus: VirtualBus,
        module_bus: VirtualBus,
    ) -> None:
        super().__init__(ctrl_info, registry, virtual_bus, module_bus)

    def move(self, motor: str, value: AxisLocation[str, TA]) -> None:  # noqa: D102
        # inherited docstring
        self._registry.motors[motor].set(value)

    def location(self, motor: str) -> AxisLocation[str, TA]:  # noqa: D102
        # inherited docstring
        return self._registry.motors[motor].locate()

    def registration_phase(self) -> None:  # noqa: D102
        # inherited docstring
        # TODO: implement
        ...

    def connection_phase(self) -> None:  # noqa: D102
        # inherited docstring
        # TODO: implement
        ...

    def shutdown(self) -> None:  # noqa: D102
        # inherited docstring
        for motor in self._registry.motors.values():
            if hasattr(motor, "shutdown"):
                motor.shutdown()
