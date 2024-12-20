r"""Motor controller module. It provides a basic protocol to interface with motorized devices.

Motor controllers are the direct link between the respective models and the user interface. \
Signals emitted from the UI are captured by the controller, and are appropriately \
translated into commands that the motor can execute. Usually when a workflow is running, \
this connection is disabled to prevent accidental user input from interfering with the workflow execution.
"""

from __future__ import annotations

from abc import abstractmethod

from typing import Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Union, Optional

    from redsun.virtual import HardwareVirtualBus


class MotorControllerProtocol(Protocol):
    """Motor controller protocol."""

    _virtual_bus: HardwareVirtualBus
    _current_locations: dict[str, Union[int, float, str]]

    @abstractmethod
    def move(
        self, motor: str, value: Union[int, float, str], axis: Optional[str] = None
    ) -> None:
        """Move the motor."""
        ...

    @abstractmethod
    def location(self, motor: str) -> Union[int, float, str]:
        """Get the motor location."""
        ...
