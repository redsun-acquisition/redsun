"""Motor controller module. It provides a basic protocol to interface with motorized devices."""

from abc import abstractmethod

from typing import Protocol, TypeAlias, TYPE_CHECKING

from sunflare.types import AxisLocation

if TYPE_CHECKING:
    from typing import Union

TA: TypeAlias = "Union[int, float, str]"


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
