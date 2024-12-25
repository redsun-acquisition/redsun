"""RedSun core virtual bus implementation."""

from __future__ import annotations

from typing import final

from sunflare.virtual import Signal, VirtualBus

__all__ = ["HardwareVirtualBus"]


@final
class HardwareVirtualBus(VirtualBus):
    r"""
    Hardware virtual bus.

    All plugins within RedSun have access to this bus to expose signals for interfacing with upper layers.
    See the `VirtualBus` class for API information.

    Attributes
    ----------
    sigStepperStep: Signal(str, str)
        - Emitted when the user clicks the up button for a stepper motor axis.
        - `Carries`: motor name, axis.
        - `Source`: ``StepperMotorWidget``.
    sigStepperStepDown: Signal(str, str)
        - Emitted when the user clicks the down button for a stepper motor axis.
        - `Carries`: motor name, axis.
        - `Source`: ``StepperMotorWidget``.
    sigStepperStepSizeChanged: Signal(str, str, float)
        - Emitted when the user changes the step size for a stepper motor axis.
        - `Carries`: motor name, axis, new step size.
        - `Source`: ``StepperMotorWidget``.
    sigNewImage: Signal(...)
        - TODO: type to be defined yet.
        - Emitted when a new image is available.
        - `Carries`: image buffer.
        - `Source`: ``DetectorController``.
    """

    sigStepperStepUp: Signal = Signal(str, str)
    sigStepperStepDown: Signal = Signal(str, str)
    sigStepperStepSizeChanged: Signal = Signal(str, str, float)
    sigNewImage: Signal = Signal()
