"""ExEngine motor controller module."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeAlias

from inspect import signature

from sunflare.controller.exengine import ExEngineController
from sunflare.virtualbus import Signal, slot
from sunflare.config import MotorModelTypes
from sunflare.types import AxisLocation

if TYPE_CHECKING:
    from typing import Union

    from redsun.controller.virtualbus import HardwareVirtualBus

    from sunflare.config import ControllerInfo
    from sunflare.virtualbus import VirtualBus
    from sunflare.engine.exengine.registry import ExEngineDeviceRegistry

TA: TypeAlias = Union[int, float]


class MotorController(ExEngineController):
    """Motor controller class.

    Parameters
    ----------
    ctrl_info : ControllerInfo
        Controller information.
    registry : ExEngineDeviceRegistry
        Device registry for ExEngine models.
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
    """

    _virtual_bus: HardwareVirtualBus

    current_locations: dict[str, AxisLocation[TA]] = {}

    sigMoveDone: Signal = Signal(str, MotorModelTypes, AxisLocation[TA])
    sigLocation: Signal = Signal(str, AxisLocation[TA])

    def __init__(
        self,
        ctrl_info: ControllerInfo,
        registry: ExEngineDeviceRegistry,
        virtual_bus: HardwareVirtualBus,
        module_bus: VirtualBus,
    ) -> None:
        super().__init__(ctrl_info, registry, virtual_bus, module_bus)
        for motor in registry.motors:
            # initialize the current locations
            self.current_locations[motor] = {
                "axis": {ax: 0 for ax in registry.motors[motor].axes},
            }

    def move(self, motor: str, value: AxisLocation[TA]) -> None:  # noqa: D102
        device = self._registry.motors[motor]
        # TODO: the device interface has to be addressed in ExEngine
        if len(signature(device.set_position).parameters) == 1:
            for ax in value["axis"].items():
                device.set_position(float(ax))  # type: ignore
        else:
            device.set_position(float(value["axis"]["x"]), float(value["axis"]["y"]))  # type: ignore

    def location(self, motor: str) -> AxisLocation[TA]:  # noqa: D102
        # inherited docstring
        position = self._registry.motors[motor].get_position()
        axis = self._registry.motors[motor].axes
        if type(position) is tuple:
            location = AxisLocation(axis={ax: position[i] for i, ax in enumerate(axis)})
        else:
            # TODO: this type hint is wrong; needs to be
            # adjusted in ExEngine
            location = AxisLocation(axis={axis: position})  # type: ignore
        return location

    def registration_phase(self) -> None:  # noqa: D102
        # inherited docstring
        ...

    def connection_phase(self) -> None:  # noqa: D102
        # inherited docstring
        # outgoing
        self.sigMoveDone.connect(self._virtual_bus.sigMoveDone)
        # ingoing
        self._virtual_bus.sigStepperStepUp.connect(self.move_up)

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
        step_size = self._registry.motors[motor].step_size
        current = self.location(motor)["axis"][axis]
        self.move(motor, AxisLocation(axis={axis: current + step_size}))

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
        step_size = self._registry.motors[motor].step_size
        current = self.location(motor)["axis"][axis]
        self.move(motor, AxisLocation(axis={axis: current - step_size}))
