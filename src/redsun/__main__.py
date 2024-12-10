"""RedSun main entry point."""

from sunflare.virtualbus import ModuleVirtualBus
from sunflare.config import RedSunInstanceInfo

from redsun.controller.virtualbus import HardwareVirtualBus


def main() -> None:
    """Redsun application entry point."""
    module_bus = ModuleVirtualBus()
    hardware_bus = HardwareVirtualBus()
