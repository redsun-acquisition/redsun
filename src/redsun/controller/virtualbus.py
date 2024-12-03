"""RedSun core virtual bus implementation."""

from __future__ import annotations

from typing import final, TYPE_CHECKING, TypeAlias

from sunflare.virtualbus import VirtualBus
from sunflare.virtualbus import Signal
from sunflare.types import AxisLocation
from sunflare.config import MotorModelTypes

if TYPE_CHECKING:
    from typing import Optional, ClassVar, Union

__all__ = ["HardwareVirtualBus"]

TA: TypeAlias = Union[int, float, str]


@final
class HardwareVirtualBus(VirtualBus):
    r"""
    Hardware virtual bus.

    All plugins within RedSun have access to this bus to expose signals for interfacing with upper layers.
    See the `VirtualBus` class for API information.

    Signals
    -------
    sigStepperStep: Signal(str, str)
        Emitted when the user clicks the up button for a stepper motor axis.
        Carries: motor name, axis.
        Source: `StepperMotorWidget`.
    sigStepperStepDown: Signal(str, str)
        Emitted when the user clicks the down button for a stepper motor axis.
        Carries: motor name, axis.
        Source: `StepperMotorWidget`.
    sigStepperStepSizeChanged: Signal(str, str, float)
        Emitted when the user changes the step size for a stepper motor axis.
        Carries: motor name, axis, new step size.
        Source: `StepperMotorWidget`.
    """

    sigStepperStepUp: Signal = Signal(str, str)
    sigStepperStepDown: Signal = Signal(str, str)
    sigStepperStepSizeChanged: Signal = Signal(str, str, float)
    sigMoveDone: Signal = Signal(str, MotorModelTypes, AxisLocation[TA])

    __instance: ClassVar[Optional[HardwareVirtualBus]] = None

    def __new__(cls) -> HardwareVirtualBus:  # noqa: D102
        if cls.__instance is None:
            cls.__instance = super(HardwareVirtualBus, cls).__new__(cls)

        return cls.__instance
