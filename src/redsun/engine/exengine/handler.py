"""ExEngine handler module."""

from typing import TYPE_CHECKING

from exengine import ExecutionEngine
from sunflare.engine import EngineHandler

if TYPE_CHECKING:
    from typing import Optional

    from sunflare.config import RedSunInstanceInfo
    from sunflare.virtualbus import VirtualBus


class ExEngineHandler(EngineHandler[ExecutionEngine]):
    r"""
    ExEngine handler class.

    All models compatible with ExEngine are registered here at application startup.

    Parameters
    ----------
    config_options : RedSunInstanceInfo
        Configuration options for the RedSun instance.
    virtual_bus : VirtualBus
        The virtual bus instance for the RedSun instance.
    module_bus : VirtualBus
        The virtual bus instance for the module.
    """

    __instance: "Optional[ExEngineHandler]" = None

    def __init__(
        self,
        config_options: "RedSunInstanceInfo",
        virtual_bus: "VirtualBus",
        module_bus: "VirtualBus",
    ):
        self._config_options = config_options
        self._virtual_bus = virtual_bus
        self._module_bus = module_bus
        self._engine = ExecutionEngine()

    def shutdown(self) -> None:  # noqa: D102
        self._engine.shutdown()

    @classmethod
    def instance(cls) -> "ExEngineHandler":
        """Return global ExEngineHandler singleton instance."""
        if cls.__instance is None:
            raise ValueError("BlueskyHandler instance not initialized.")
        return cls.__instance

    @property
    def engine(self) -> ExecutionEngine:
        """Execution engine instance."""
        return self._engine
