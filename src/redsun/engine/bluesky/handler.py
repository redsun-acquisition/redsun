"""Bluesky handler class."""

from typing import TYPE_CHECKING, final

from bluesky.run_engine import RunEngine
from sunflare.engine import EngineHandler
from sunflare.log import Loggable

if TYPE_CHECKING:
    from typing import Optional

    from sunflare.types import Workflow
    from sunflare.config import RedSunInstanceInfo
    from sunflare.virtualbus import VirtualBus


@final
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
    _workflows: dict[str, "Workflow"] = {}

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
        """Invoke "stop" method on the run engine.

        "stop" marks it as successfull.
        """
        self._engine.stop()  # type: ignore[no-untyped-call]

    def register_workflows(self, name: str, workflow: "Workflow") -> None:
        """Register a workflow with the handler."""
        if not name in self._workflows.keys():
            self._workflows[name] = workflow
        else:
            self.error(f"Workflow {name} already registered. Aborted.")

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

    @property
    def workflows(self) -> dict[str, "Workflow"]:
        """Workflow dictionary."""
        return self._workflows
