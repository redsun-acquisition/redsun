"""Bluesky handler class."""

from __future__ import annotations

from typing import TYPE_CHECKING, final, Any

from bluesky.run_engine import RunEngine
from bluesky.utils import MsgGenerator
from sunflare.engine.handler import EngineHandler
from sunflare.log import Loggable

if TYPE_CHECKING:
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
        self._plans: dict[str, MsgGenerator[Any]] = {}
        self._engine = RunEngine()  # type: ignore[no-untyped-call]

    def shutdown(self) -> None:
        """Invoke "stop" method on the run engine.

        "stop" marks it as successfull.
        """
        self._engine.stop()  # type: ignore[no-untyped-call]

    def register_plan(self, name: str, plan: MsgGenerator[Any]) -> None:
        """Register a workflow with the handler."""
        if not name in self._plans.keys():
            self._plans[name] = plan
        else:
            self.error(f"Workflow {name} already registered. Aborted.")

    @property
    def engine(self) -> RunEngine:
        """Execution engine instance."""
        return self._engine

    @property
    def plans(self) -> dict[str, MsgGenerator[Any]]:
        """Workflow dictionary."""
        return self._plans
