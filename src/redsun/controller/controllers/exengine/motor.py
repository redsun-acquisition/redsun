"""ExEngine motor controller module."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeAlias, Sequence

from sunflare.controller.exengine import ExEngineController

if TYPE_CHECKING:
    from typing import Union

    from sunflare.types import AxisLocation
    from sunflare.config import ControllerInfo
    from sunflare.virtualbus import VirtualBus
    from sunflare.engine.exengine.registry import ExEngineDeviceRegistry

TA: TypeAlias = Union[int, float, str]


class MotorController(ExEngineController):
    """Motor controller class."""

    def __init__(
        self,
        ctrl_info: ControllerInfo,
        registry: ExEngineDeviceRegistry,
        virtual_bus: VirtualBus,
        module_bus: VirtualBus,
    ) -> None:
        super().__init__(ctrl_info, registry, virtual_bus, module_bus)

    def move(self, motor: str, value: AxisLocation[str, TA]) -> None:  # noqa: D102
        # TODO: this is a typing hell due to the fact that ExEngine
        # has a too strict distinction between single and double
        # axis motors. The call will be correct because the
        # proper motor is created elsewhere, but it's best to fix this in ExEngine.
        if isinstance(value["axis"], Sequence):
            # TODO: what happens if the motor has not X and Y axis?
            x, y = (value["setpoint"][0], value["setpoint"][1])  # type: ignore
            self._registry.motors[motor].set_position(x, y)  # type: ignore
        else:
            self._registry.motors[motor].set_position(value["setpoint"])  # type: ignore

    def location(self, motor: str) -> AxisLocation[str, TA]:  # noqa: D102
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
