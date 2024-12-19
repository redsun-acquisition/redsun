r"""Motor controller module. It provides a basic protocol to interface with motorized devices.

Motor controllers are the direct link between the respective models and the user interface. \
Signals emitted from the UI are captured by the controller, and are appropriately \
translated into commands that the motor can execute. Usually when a workflow is running, \
this connection is disabled to prevent accidental user input from interfering with the workflow execution.
"""

from __future__ import annotations

from abc import abstractmethod

from typing import Protocol, TypeAlias, TYPE_CHECKING

from sunflare.types import Location

if TYPE_CHECKING:
    from typing import Union

    from redsun.virtual import HardwareVirtualBus

TA: TypeAlias = Union[int, float]


class MotorControllerProtocol(Protocol):
    """Motor controller protocol."""

    _virtual_bus: HardwareVirtualBus
    _current_locations: dict[str, Location[TA]]

    @abstractmethod
    def move(self, motor: str, value: Location[TA]) -> None:
        """Move the motor."""
        ...

    @abstractmethod
    def location(self, motor: str) -> None:
        """Get the motor location.

        The motor location is not returned directly,
        but instead is kept cached in the `__current_locations` dictionary.
        A signal may be emitted to notify the UI of the new location.
        """
        ...
