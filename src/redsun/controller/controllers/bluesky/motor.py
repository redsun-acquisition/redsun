"""Bluesky motor controller module."""

from __future__ import annotations

from typing import TypeAlias, Union

from sunflare.engine.registry import DeviceRegistry
from sunflare.controller import BaseController
from sunflare.virtualbus import Signal, slot
from sunflare.config import MotorModelTypes, ControllerInfo
from sunflare.types import Location
from sunflare.virtualbus import VirtualBus
from sunflare.log import Loggable

from redsun.virtual import HardwareVirtualBus

TA: TypeAlias = Union[float, int, str]


class MotorController(BaseController, Loggable):
    """Motor controller class.

    Parameters
    ----------
    ctrl_info : ControllerInfo
        Controller information.
    registry : DeviceRegistry
        Device registry for Bluesky models.
    virtual_bus : HardwareVirtualBus
        Virtual bus for the main module (hardware control).
    module_bus : VirtualBus
        Inter-module virtual bus.

    Signals
    -------
    sigMoveDone : Signal(str, MotorModelTypes, dict[str, Location[Union[int, float, str]]])
        Emitted when a motor has finished moving.
        Carries:
        - motor name;
        - motor model category;
        - motor location (dict[str, Location[Union[int, float, str]]]).
    sigLocation : Signal(str, dict[str, Location[Union[int, float, str]]])
        Emitted when a motor location is requested.
        Carries:
        - motor name;
        - motor location.

    Slots
    -----
    move_up : str, str
        Move the motor in the positive direction.
        Expects:
        - motor name;
        - axis name.
    move_down : str, str
        Move the motor in the negative direction.
        Expects:
        - motor name;
        - axis name.
    """

    _virtual_bus: HardwareVirtualBus

    sigMoveDone: Signal = Signal(str, MotorModelTypes, dict[str, Location[TA]])
    sigLocation: Signal = Signal(str, dict[str, Location[TA]])

    def __init__(
        self,
        ctrl_info: ControllerInfo,
        registry: DeviceRegistry,
        virtual_bus: HardwareVirtualBus,
        module_bus: VirtualBus,
    ) -> None:
        super().__init__(ctrl_info, registry, virtual_bus, module_bus)

    def move(self, motor: str, value: dict[str, Location[TA]]) -> None:  # noqa: D102
        # inherited docstring
        self._registry.motors[motor].set(value)

    def location(self, motor: str) -> dict[str, Location[TA]]:  # noqa: D102
        # inherited docstring
        return self._registry.motors[motor].locate()

    def registration_phase(self) -> None:  # noqa: D102
        # inherited docstring
        # nothing to do here
        ...

    def connection_phase(self) -> None:  # noqa: D102
        # inherited docstring
        self.sigMoveDone.connect(self._virtual_bus.sigMoveDone)
        self._virtual_bus.sigStepperStepUp.connect(self.move_up)
        self._virtual_bus.sigStepperStepDown.connect(self.move_down)

    def shutdown(self) -> None:  # noqa: D102
        # inherited docstring
        for motor in self._registry.motors.values():
            if hasattr(motor, "shutdown"):
                motor.shutdown()

    @slot
    def move_up(self, motor: str, axis: str) -> None:
        """Move the motor in the positive direction.

        Step size is determined by the chosen motor model.

        Parameters
        ----------
        motor : str
            Motor name.
        axis : str
            Motor axis along which movement occurs.
        """
        step_size = self._registry.motors[motor].model_info.step_size
        current = self.location(motor)
        if isinstance(current[axis]["setpoint"], (int, float)):
            self.move(
                motor,
                {
                    axis: Location(
                        setpoint=current[axis]["setpoint"] + step_size,  # type: ignore[operator]
                        readback=current[axis]["setpoint"],
                    )
                },
            )
        else:
            self.move(
                motor,
                {
                    axis: Location(
                        setpoint=current[axis]["setpoint"],
                        readback=current[axis]["setpoint"],
                    )
                },
            )

    @slot
    def move_down(self, motor: str, axis: str) -> None:
        """Move the motor in the negative direction.

        Step size is determined by the chosen motor model.

        Parameters
        ----------
        motor : str
            Motor name.
        axis : str
            Motor axis along which movement occurs.
        """
        step_size = self._registry.motors[motor].model_info.step_size
        current = self.location(motor)
        if isinstance(current[axis]["setpoint"], (int, float)):
            self.move(
                motor,
                {
                    axis: Location(
                        setpoint=current[axis]["setpoint"] - step_size,  # type: ignore[operator]
                        readback=current[axis]["setpoint"],
                    )
                },
            )
        else:
            self.move(
                motor,
                {
                    axis: Location(
                        setpoint=current[axis]["setpoint"],
                        readback=current[axis]["setpoint"],
                    )
                },
            )
