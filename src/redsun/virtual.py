"""RedSun core virtual bus implementation."""

from __future__ import annotations

from typing import Any, final

from numpy.typing import NDArray
from sunflare.virtual import Signal, VirtualBus

__all__ = ["HardwareVirtualBus"]


@final
class HardwareVirtualBus(VirtualBus):
    r"""
    Hardware virtual bus.

    All plugins within RedSun have access to this bus to expose signals for interfacing with upper layers.
    See the `VirtualBus` class for API information.

    Signals
    ----------
    sigStepperStep: ``Signal(str, str, str)``
        - Emitted when the user clicks the up button for a stepper motor axis.
        - `Carries`: motor name, axis, direction (north, or south).
        - `Source`: ``MotorWidget``.
    sigStepperStepSizeChanged: Signal(str, str, float)
        - Emitted when the user changes the step size for a stepper motor axis.
        - `Carries`: motor name, axis, new step size.
        - `Source`: ``MotorWidget``.
    sigNewImage: Signal(dict[str, NDArray[Any]])
        - Emitted when a new image is available.
        - `Carries`: image data.
        - `Source`: ``DetectorController``.
    """

    sigStep: Signal = Signal(str, str, str)
    sigStepSizeChanged: Signal = Signal(str, str, float)
    sigNewImage: Signal = Signal(dict[str, NDArray[Any]])
