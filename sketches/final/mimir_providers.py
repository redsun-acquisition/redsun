# ruff: noqa
"""What redsun_mimir/providers.py becomes.

Same purpose and the same eleven names: the shared vocabulary of the bundle,
declared where consumers can import it. What is gone is the plumbing. There is
no Provider class here, because each presenter carries its own - see
`@provides` in `mimir_app.py`.

`dip.Dependency(instance_of=dict)` accepted any dict and checked nothing.
`NewType` is checked by the type checker at every provide and every consume,
and is what lets four keys that are all `dict[str, Reading[Any]]` stay
distinct in a type-keyed container.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, NewType

if TYPE_CHECKING:
    from bluesky.protocols import Descriptor, Reading
    from ophyd_async.core import SignalR

    from redsun_mimir.protocols import LayerSpec

#: Configuration descriptors of every detector, by data key.
DetectorDescriptors = NewType("DetectorDescriptors", "dict[str, Descriptor]")

#: Current configuration readings of every detector, by data key.
DetectorReadings = NewType("DetectorReadings", "dict[str, Reading[Any]]")

#: Shape and dtype of the image layer each detector feeds, by device name.
DetectorLayerSpecs = NewType("DetectorLayerSpecs", "dict[str, LayerSpec]")

#: Current readings of every motor axis, by data key.
MotorReadings = NewType("MotorReadings", "dict[str, Reading[Any]]")

#: Descriptors of every motor axis, by data key.
MotorDescription = NewType("MotorDescription", "dict[str, Descriptor]")

#: Readback signal of every motor axis, by data key. Unlike the two above this
#: is the live signal, so a subscriber sees every move, including a plan's.
MotorReadbacks = NewType("MotorReadbacks", "dict[str, SignalR[float]]")

#: Current readings of every light source, by data key.
LightConfiguration = NewType("LightConfiguration", "dict[str, Reading[Any]]")

#: Descriptors of every light source, by data key.
LightDescription = NewType("LightDescription", "dict[str, Descriptor]")

#: Current readings of every stated device, by data key.
StatedConfiguration = NewType("StatedConfiguration", "dict[str, Reading[Any]]")

#: Descriptors of every stated device, by data key. The ``choices`` field of
#: each descriptor is what a selector is built from.
StatedDescription = NewType("StatedDescription", "dict[str, Descriptor]")

#: Specifiers of the plans the acquisition presenter can launch.
PlanSpecs = NewType("PlanSpecs", "set[Any]")

__all__ = [
    "DetectorDescriptors",
    "DetectorLayerSpecs",
    "DetectorReadings",
    "LightConfiguration",
    "LightDescription",
    "MotorDescription",
    "MotorReadbacks",
    "MotorReadings",
    "PlanSpecs",
    "StatedConfiguration",
    "StatedDescription",
]
