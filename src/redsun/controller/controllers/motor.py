r"""Motor controller module. It provides a basic protocol to interface with motorized devices.

Motor controllers are the direct link between the respective models and the user interface. \
Signals emitted from the UI are captured by the controller, and are appropriately \
translated into commands that the motor can execute. Usually when a workflow is running, \
this connection is disabled to prevent accidental user input from interfering with the workflow execution.
"""

from __future__ import annotations

from abc import abstractmethod

from typing import Protocol, TypeAlias, TYPE_CHECKING

from sunflare.types import AxisLocation

if TYPE_CHECKING:
    from typing import Union

TA: TypeAlias = Union[int, float, str]


class MotorControllerProtocol(Protocol):
    """Motor controller protocol."""

    @abstractmethod
    def move(self, motor: str, value: AxisLocation[str, TA]) -> None:
        """Move the motor."""
        ...

    @abstractmethod
    def location(self, motor: str) -> AxisLocation[str, TA]:
        """Get the motor location."""
        ...
