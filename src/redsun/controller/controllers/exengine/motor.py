"""Stepper motor controller module."""

from typing import TYPE_CHECKING, TypeAlias, Sequence

from sunflare.controller.exengine import ExEngineController

if TYPE_CHECKING:
    from typing import Union

    from sunflare.types import AxisLocation
    from sunflare.config import ControllerInfo
    from sunflare.virtualbus import VirtualBus
    from sunflare.engine.exengine.registry import ExEngineDeviceRegistry

TA: TypeAlias = "Union[int, float, str]"


class StepperController(ExEngineController):
    """Stepper motor controller class."""

    def __init__(
        self,
        ctrl_info: "ControllerInfo",
        registry: "ExEngineDeviceRegistry",
        virtual_bus: "VirtualBus",
        module_bus: "VirtualBus",
    ) -> None:
        super().__init__(ctrl_info, registry, virtual_bus, module_bus)

    def move(self, motor: str, value: AxisLocation[TA, str]) -> None:  # noqa: D102
        # TODO: the API is too specific, needs to be adjusted
        # in exengine
        # if isinstance(value["axis"], Sequence):
        #     # TODO: what happens if the motor has not X and Y axis?
        #     x, y = (value["setpoint"][0], value["setpoint"][1])
        #     self._registry.motors[motor].set_position(x, y)
        # else:
        #     self._registry.motors[motor].set_position(value["setpoint"])
        raise NotImplementedError

    def location(self, motor: str) -> AxisLocation[TA, str]:  # noqa: D102
        # inherited docstring
        position = self._registry.motors[motor].get_position()
        axis = self._registry.motors[motor].axes
        return {"axis": axis, "setpoint": position, "readback": position}

    def registration_phase(self) -> None:  # noqa: D102
        # inherited docstring
        ...

    def connection_phase(self) -> None:  # noqa: D102
        # inherited docstring
        ...

    def shutdown(self) -> None:  # noqa: D102
        # inherited docstring
        for motor in self._registry.motors.values():
            if hasattr(motor, "shutdown"):
                motor.shutdown()
