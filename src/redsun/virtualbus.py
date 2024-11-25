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

    _instance: "Optional[HardwareVirtualBus]" = None

    def __new__(cls) -> "HardwareVirtualBus": # noqa: D104
        # singleton pattern
        if cls._instance is None:
            cls._instance = object.__new__(cls)
        return cls._instance
