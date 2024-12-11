"""ExEngine handler module."""

from typing import TYPE_CHECKING, final

from exengine import ExecutionEngine
from sunflare.engine.handler import EngineHandler
from sunflare.log import Loggable

if TYPE_CHECKING:
    from typing import Optional

    from sunflare.types import Workflow
    from sunflare.config import RedSunInstanceInfo
    from sunflare.virtualbus import VirtualBus


@final
class ExEngineHandler(EngineHandler[ExecutionEngine], Loggable):
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
    _workflows: dict[str, "Workflow"] = {}

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
        ExEngineHandler.__instance = self

    def shutdown(self) -> None:  # noqa: D102
        self._engine.shutdown()

    def register_workflows(self, name: str, workflow: "Workflow") -> None:  # noqa: D102
        if not name in self._workflows.keys():
            self._workflows[name] = workflow
        else:
            self.error(f"Workflow {name} already registered. Aborted.")

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

    @property
    def workflows(self) -> "dict[str, Workflow]":
        """Return registered workflows."""
        return self._workflows
