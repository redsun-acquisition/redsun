"""Bluesky motor controller module."""

from __future__ import annotations

from typing import TypeAlias, Union

from sunflare.engine.bluesky.registry import BlueskyDeviceRegistry
from sunflare.controller.bluesky import BlueskyController
from sunflare.virtualbus import Signal, slot
from sunflare.config import MotorModelTypes, ControllerInfo
from sunflare.types import AxisLocation
from sunflare.virtualbus import VirtualBus

from redsun.virtual import HardwareVirtualBus

TA: TypeAlias = Union[float, str]


class MotorController(BlueskyController):
    """Motor controller class.

    Parameters
    ----------
    ctrl_info : ControllerInfo
        Controller information.
    registry : BlueskyDeviceRegistry
        Device registry for Bluesky models.
    virtual_bus : HardwareVirtualBus
        Virtual bus for the main module (hardware control).
    module_bus : VirtualBus
        Inter-module virtual bus.

    Attributes
    ----------
    current_locations : dict[str, AxisLocation[Union[int, float]]]
        Dictionary of current motor locations.

    Signals
    -------
    sigMoveDone : Signal(str, MotorModelTypes, AxisLocation[Union[int, float]])
        Emitted when a motor has finished moving.
        Carries:
        - motor name;
        - motor model category;
        - motor location (AxisLocation[Union[int, float]]).
    sigLocation : Signal(str, AxisLocation[Union[int, float]])
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

    sigMoveDone: Signal = Signal(str, MotorModelTypes, AxisLocation[TA])
    sigLocation: Signal = Signal(str, AxisLocation[TA])

    def __init__(
        self,
        ctrl_info: ControllerInfo,
        registry: BlueskyDeviceRegistry,
        virtual_bus: HardwareVirtualBus,
        module_bus: VirtualBus,
    ) -> None:
        super().__init__(ctrl_info, registry, virtual_bus, module_bus)

    def move(self, motor: str, value: AxisLocation[TA]) -> None:  # noqa: D102
        # inherited docstring
        self._registry.motors[motor].set(value)

    def location(self, motor: str) -> AxisLocation[TA]:  # noqa: D102
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
        current = self.location(motor)["axis"][axis]
        if isinstance(current, (int, float)):
            self.move(motor, AxisLocation(axis={axis: current + step_size}))
        else:
            self.move(motor, AxisLocation(axis={axis: current}))

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
        current = self.location(motor)["axis"][axis]
        if isinstance(current, (int, float)):
            self.move(motor, AxisLocation(axis={axis: current - step_size}))
        else:
            self.move(motor, AxisLocation(axis={axis: current}))
