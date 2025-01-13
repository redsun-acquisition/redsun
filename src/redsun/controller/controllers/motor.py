"""Bluesky motor controller module."""

from __future__ import annotations

from operator import add, sub
from typing import TYPE_CHECKING, Union, cast

from sunflare.config import MotorInfo
from sunflare.controller import ControllerProtocol
from sunflare.log import Loggable
from sunflare.model import MotorModelProtocol
from sunflare.virtual import Signal, slot

if TYPE_CHECKING:
    from typing import Optional

    from sunflare.virtual import ModuleVirtualBus

    from redsun.controller.config import MotorControllerInfo
    from redsun.engine.bluesky.handler import BlueskyHandler
    from redsun.virtual import HardwareVirtualBus


class MotorController(ControllerProtocol, Loggable):
    """Motor controller class.

    Parameters
    ----------
    ctrl_info : ``MotorControllerInfo``
        Controller information.
    handler: ``BlueskyHandler``
        Bluesky engine handler.
    virtual_bus : ``HardwareVirtualBus``
        Virtual bus for the main module (hardware control).
    module_bus : ``ModuleVirtualBus``
        Inter-module virtual bus.

    Signals
    -------
    sigNewPosition : ``Signal(str, str, Union[int, float])``
        Emitted when a motor location is updated. Carries:
        - motor name;
        - axis name;
        - updated motor location.
    """

    _virtual_bus: HardwareVirtualBus

    sigNewPosition: Signal = Signal(str, str, object)

    def __init__(
        self,
        ctrl_info: MotorControllerInfo,
        handler: BlueskyHandler,
        virtual_bus: HardwareVirtualBus,
        module_bus: ModuleVirtualBus,
    ) -> None:
        self._ctrl_info = ctrl_info
        self._handler = handler
        self._virtual_bus = virtual_bus
        self._module_bus = module_bus

        self._ops = {"north": add, "south": sub}

        # get a list of models to be used;
        # if none are specified, use all available models
        models: Optional[list[str]] = self._ctrl_info.models
        if models is None:
            models = [
                name
                for name in handler.models
                if isinstance(handler.models[name], MotorModelProtocol)
            ]

        self._motors: dict[str, MotorModelProtocol] = {
            name: cast(MotorModelProtocol, handler.models[name]) for name in models
        }

        model_infos: dict[str, MotorInfo] = {
            name: cast(MotorInfo, motor.model_info)
            for name, motor in self._motors.items()
        }

        # update the controller info with the available models
        self._ctrl_info.models = models
        self._ctrl_info.axis = {name: motor.axis for name, motor in model_infos.items()}
        self._ctrl_info.step_sizes = {
            name: motor.step_size for name, motor in model_infos.items()
        }
        self._ctrl_info.egu = {name: motor.egu for name, motor in model_infos.items()}

    @slot
    def on_move_rel(self, motor: str, axis: str, direction: str) -> None:
        """Move the motor along the axis in a specified direction.

        The movement is relative to the current motor location and the step size.

        Parameters
        ----------
        motor : str
            Motor name.
        axis : str
            Motor axis along which movement occurs.
        direction : str
            Movement direction ("north", or "south").
        """
        obj = self._motors[motor]
        info = cast(MotorInfo, obj.model_info)
        new_value = self._ops[direction](self.location(motor), info.step_size[axis])
        status = obj.set(new_value, axis)

        # wait for the operation to complete
        # TODO: this is very bad; we should not block the main thread;
        #       must find another way to handle this; possibly implementing
        #       the status object differently
        while not status.done:
            ...
        self.sigNewPosition.emit(motor, new_value)

    @slot
    def on_step_size_changed(self, motor: str, axis: str, step_size: float) -> None:
        """Change the motor step size.

        Parameters
        ----------
        motor : str
            Motor name.
        axis : str
            Motor axis.
        step_size : float
            New step size.
        """
        info = cast(MotorInfo, self._motors[motor].model_info)
        info.step_size[axis] = step_size

    def location(self, motor: str) -> Union[int, float]:
        """Get the current motor location.

        Parameters
        ----------
        motor : str
            Motor name.

        Returns
        -------
        Union[int, float]
            Motor current setpoint.
        """
        return self._motors[motor].locate()["setpoint"]

    def registration_phase(self) -> None:
        """Register signals to the virtual layer."""
        # nothing to do here
        ...

    def connection_phase(self) -> None:
        """Connect the controller to the virtual layer."""
        self._virtual_bus.sigStep.connect(self.on_move_rel)
        self._virtual_bus.sigStepSizeChanged.connect(self.on_step_size_changed)

    def shutdown(self) -> None:  # noqa: D102
        # inherited docstring
        for motor in self._motors.values():
            if hasattr(motor, "shutdown"):
                motor.shutdown()
