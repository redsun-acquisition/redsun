"""Bluesky handler class."""

from __future__ import annotations

from typing import TYPE_CHECKING, final

from bluesky.run_engine import RunEngine
from sunflare.engine.handler import EngineHandler
from sunflare.log import Loggable

if TYPE_CHECKING:
    from sunflare.types import Workflow
    from sunflare.virtualbus import VirtualBus


@final
class BlueskyHandler(EngineHandler, Loggable):
    """
    Bluesky handler class.

    Parameters
    ----------
    config_options : RedSunInstanceInfo
        Configuration options for the RedSun instance.
    virtual_bus : VirtualBus
        The virtual bus instance for the RedSun instance.
    module_bus : VirtualBus
        The virtual bus instance for the module.
    """

    def __init__(
        self,
        virtual_bus: VirtualBus,
        module_bus: VirtualBus,
    ) -> None:
        self._virtual_bus = virtual_bus
        self._module_bus = module_bus
        self._workflows: dict[str, Workflow] = {}
        self._engine = RunEngine()  # type: ignore[no-untyped-call]

    def shutdown(self) -> None:
        """Invoke "stop" method on the run engine.

        "stop" marks it as successfull.
        """
        self._engine.stop()  # type: ignore[no-untyped-call]

    def register_workflows(self, name: str, workflow: Workflow) -> None:
        """Register a workflow with the handler."""
        if not name in self._workflows.keys():
            self._workflows[name] = workflow
        else:
            self.error(f"Workflow {name} already registered. Aborted.")

    @property
    def engine(self) -> RunEngine:
        """Execution engine instance."""
        return self._engine

    @property
    def workflows(self) -> dict[str, Workflow]:
        """Workflow dictionary."""
        return self._workflows
