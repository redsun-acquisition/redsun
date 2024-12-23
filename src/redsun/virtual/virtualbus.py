"""RedSun core virtual bus implementation."""

from __future__ import annotations

from typing import TypeAlias, Union, final

from sunflare.config import DetectorModelInfo, MotorModelInfo, MotorModelTypes
from sunflare.engine import DetectorModel, MotorModel
from sunflare.virtualbus import Signal, VirtualBus

__all__ = ["HardwareVirtualBus"]

TA: TypeAlias = Union[int, float, str]
Registry: TypeAlias = dict[
    str, Union[DetectorModel[DetectorModelInfo], MotorModel[MotorModelInfo]]
]


@final
class HardwareVirtualBus(VirtualBus):
    r"""
    Hardware virtual bus.

    All plugins within RedSun have access to this bus to expose signals for interfacing with upper layers.
    See the `VirtualBus` class for API information.

    Attributes
    ----------
    sigNewDevices: Signal(str, dict[str, Union[DetectorModel, MotorModel]])
        - Emitted when a new group of device plugins is loaded.
        - `Carries`: the device group to which the plugins belong (i.e. "motors"), dictionary of plugins (key: plugin name, value: plugin instance).
        - `Source`: ``PluginManager``.
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
    sigMoveDone: Signal(str, MotorModelTypes, Union[int, float, str])
        - TODO: document this signal.
        - `Source`: ``MotorController``.
    sigNewImage: Signal(...)
        - TODO: type to be defined yet.
        - Emitted when a new image is available.
        - `Carries`: image buffer.
        - `Source`: ``DetectorController``.
    """

    sigNewDevices: Signal = Signal(str, Registry)
    sigStepperStepUp: Signal = Signal(str, str)
    sigStepperStepDown: Signal = Signal(str, str)
    sigStepperStepSizeChanged: Signal = Signal(str, str, float)
    sigMoveDone: Signal = Signal(str, MotorModelTypes, object)
    sigNewImage: Signal = Signal()
