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

    # TODO: these need to be documented with
    # the description field in the Signal class;
    # but first the virtual bus needs to be reworked
    sigStepperStepUp: Signal = Signal(str, str)
    sigStepperStepDown: Signal = Signal(str, str)

    __instance: ClassVar[Optional[HardwareVirtualBus]] = None

    @classmethod
    def instance(cls) -> HardwareVirtualBus:
        """Return global HardwareVirtualBus singleton instance."""
        if cls.__instance is None:
            cls.__instance = cls()
        return cls.__instance
