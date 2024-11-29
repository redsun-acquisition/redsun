"""Stepper motor controller module."""

from typing import TYPE_CHECKING, TypeAlias

from sunflare.controller.base import BaseController

if TYPE_CHECKING:
    from typing import Union

    from sunflare.config import ControllerInfo
    from sunflare.virtualbus import VirtualBus

    from redsun.engine.bluesky import BlueskyHandler


P: TypeAlias = "Union[int, float]"


class StepperController(BaseController):
    """Stepper motor controller class."""

    def __init__(
        self,
        ctrl_info: "ControllerInfo",
        handler: "BlueskyHandler",
        virtual_bus: "VirtualBus",
        module_bus: "VirtualBus",
    ) -> None:
        super().__init__(ctrl_info, handler, virtual_bus, module_bus)

    def move(self, motor: str, value: dict[str, P]) -> None:
        """Move the stepper motor."""
        ...

    def location(self, motor: str) -> dict[str, P]:
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
