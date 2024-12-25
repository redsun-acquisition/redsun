"""Bluesky motor controller module."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Union

from sunflare.controller import BaseController
from sunflare.log import Loggable
from sunflare.virtualbus import Signal, VirtualBus, slot

if TYPE_CHECKING:
    from sunflare.config import ControllerInfo

    from redsun.engine.bluesky.handler import BlueskyHandler
    from redsun.virtual import HardwareVirtualBus


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
    sigLocation : Signal(str, Location[Union[int, float, str]])
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

    sigLocation: Signal = Signal(str, object)

    def __init__(
        self,
        ctrl_info: ControllerInfo,
        handler: BlueskyHandler,
        virtual_bus: HardwareVirtualBus,
        module_bus: VirtualBus,
    ) -> None:
        super().__init__(ctrl_info, handler, virtual_bus, module_bus)

    def move(  # noqa: D102
        self, motor: str, value: Union[int, float, str], axis: Optional[str] = None
    ) -> None:
        # inherited docstring
        self._handler.motors[motor].set(value, axis=axis)

    def location(self, motor: str) -> Union[int, float, str]:  # noqa: D102
        # inherited docstring
        return self._handler.motors[motor].locate()["setpoint"]

    def registration_phase(self) -> None:  # noqa: D102
        # inherited docstring
        # nothing to do here
        ...

    def connection_phase(self) -> None:  # noqa: D102
        # inherited docstring
        self._virtual_bus.sigStepperStepUp.connect(self.move_up)
        self._virtual_bus.sigStepperStepDown.connect(self.move_down)

    def shutdown(self) -> None:  # noqa: D102
        # inherited docstring
        for motor in self._handler.motors.values():
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
        step_size = self._handler.motors[motor].model_info.step_size
        current = self.location(motor)
        if isinstance(current, (int, float)):
            self.move(motor, current + step_size, axis=axis)
        else:
            self.move(motor, current, axis=axis)

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
        step_size = self._handler.motors[motor].model_info.step_size
        current = self.location(motor)
        if isinstance(current, (int, float)):
            self.move(motor, current - step_size, axis=axis)
        else:
            self.move(motor, current, axis=axis)
