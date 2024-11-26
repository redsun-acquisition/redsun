"""RedSun core virtual bus implementation."""

from typing import final
from sunflare.virtualbus import VirtualBus
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Optional

__all__ = ["HardwareVirtualBus"]


@final
class HardwareVirtualBus(VirtualBus):
    """
    Hardware virtual bus.

    All plugins within RedSun have access to this bus to expose signals for interfacing with upper layers.
    See the `VirtualBus` class for API information.
    """

    __instance: "Optional[HardwareVirtualBus]" = None

    @classmethod
    def instance(cls) -> "HardwareVirtualBus":
        """Return global HardwareVirtualBus singleton instance."""
        if cls.__instance is None:
            cls.__instance = cls()
        return cls.__instance
