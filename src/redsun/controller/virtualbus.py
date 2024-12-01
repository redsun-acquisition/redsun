"""RedSun core virtual bus implementation."""

from __future__ import annotations

from typing import final, TYPE_CHECKING

from sunflare.virtualbus import VirtualBus
from sunflare.virtualbus import Signal

if TYPE_CHECKING:
    from typing import Optional, ClassVar

__all__ = ["HardwareVirtualBus"]


@final
class HardwareVirtualBus(VirtualBus):
    """
    Hardware virtual bus.

    All plugins within RedSun have access to this bus to expose signals for interfacing with upper layers.
    See the `VirtualBus` class for API information.
    """

    sigStepperStepUp: Signal = Signal(str, str)
    sigStepperStepDown: Signal = Signal(str, str)

    __instance: ClassVar[Optional[HardwareVirtualBus]] = None

    def __new__(cls) -> HardwareVirtualBus:  # noqa: D102
        if cls.__instance is None:
            cls.__instance = super(HardwareVirtualBus, cls).__new__(cls)

        return cls.__instance
