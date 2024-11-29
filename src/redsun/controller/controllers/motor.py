"""RedSun motor controller module."""

from abc import abstractmethod

from typing import TYPE_CHECKING, Protocol, TypeVar, Tuple, Generic, Union

if TYPE_CHECKING:
    from sunflare.virtualbus import ModuleVirtualBus

    from redsun.controller.virtualbus import HardwareVirtualBus

N = TypeVar("N", int, float)

P = TypeVar("P", bound=Union[Tuple[str, N], Tuple[str, N, N]])

T = TypeVar("T", str, Tuple[str, ...])


class MotorControllerProtocol(Protocol, Generic[T]):
    """Motor controller protocol."""

    _module_bus: "ModuleVirtualBus"
    _virtual_bus: "HardwareVirtualBus"

    @abstractmethod
    def move(self, motor: str, value: T) -> None:
        """Move the motor."""
        ...

    @abstractmethod
    def location(self, motor: str) -> T:
        """Get the motor location."""
        ...
