"""RedSun motor controller module."""

from abc import abstractmethod

from typing import Protocol, TypeVar, Generic, TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

T = TypeVar("T", bound=dict[str, "Any"])


class MotorControllerProtocol(Protocol, Generic[T]):
    """Motor controller protocol."""

    @abstractmethod
    def move(self, motor: str, value: T) -> None:
        """Move the motor."""
        ...

    @abstractmethod
    def location(self, motor: str) -> T:
        """Get the motor location."""
        ...
