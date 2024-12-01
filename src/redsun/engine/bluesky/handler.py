"""Bluesky handler class."""

from typing import TYPE_CHECKING

from bluesky.run_engine import RunEngine
from sunflare.engine import EngineHandler, DetectorModel, MotorModel
from sunflare.log import Loggable

if TYPE_CHECKING:
    from typing import Union, Optional

    from sunflare.config import RedSunInstanceInfo
    from sunflare.engine.bluesky import BlueskyDetectorModel, BlueskyMotorModel
    from sunflare.virtualbus import VirtualBus


class BlueskyHandler(EngineHandler[RunEngine], Loggable):
    r"""
    Bluesky handler class.

    All models compatible with Bluesky are registered here at application startup.

    Parameters
    ----------
    config_options : RedSunInstanceInfo
        Configuration options for the RedSun instance.
    virtual_bus : VirtualBus
        The virtual bus instance for the RedSun instance.
    module_bus : VirtualBus
        The virtual bus instance for the module.
    """

    __instance: "Optional[BlueskyHandler]" = None

    def __init__(
        self,
        config_options: "RedSunInstanceInfo",
        virtual_bus: "VirtualBus",
        module_bus: "VirtualBus",
    ) -> None:
        self._config_options = config_options
        self._virtual_bus = virtual_bus
        self._module_bus = module_bus
        self._engine = RunEngine()  # type: ignore[no-untyped-call]
        BlueskyHandler.__instance = self

    def shutdown(self) -> None:
        """Invoke "stop" method on the run engine."""
        self._engine.stop()  # type: ignore[no-untyped-call]

    @classmethod
    def instance(cls) -> "BlueskyHandler":
        """Return global BlueskyHandler singleton instance."""
        if cls.__instance is None:
            raise ValueError("BlueskyHandler instance not initialized.")
        return cls.__instance

    @property
    def engine(self) -> RunEngine:
        """Execution engine instance."""
        return self._engine
