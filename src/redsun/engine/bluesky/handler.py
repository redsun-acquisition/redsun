"""Module implementing the handler for the standard Bluesky engine."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Literal, Optional, final

from sunflare.engine import EngineHandler
from sunflare.log import Loggable

from bluesky.run_engine import RunEngine
from bluesky.utils import PlanHalt

if TYPE_CHECKING:
    from functools import partial

    from sunflare.config import RedSunSessionInfo
    from sunflare.model import ModelProtocol
    from sunflare.virtual import ModuleVirtualBus

    from bluesky.utils import DuringTask, MsgGenerator
    from redsun.virtual import HardwareVirtualBus


@final
class BlueskyHandler(EngineHandler, Loggable):
    """
    Bluesky handler class.

    Parameters
    ----------
    config : RedSunSessionInfo
        Configuration options for the RedSun session.
    virtual_bus : VirtualBus
        Reference to the virtual bus.
    module_bus : VirtualBus
        Reference to the module bus.
    during_task : DuringTask
        The DuringTask object. For more information,
        see :class:`~sunflare.engine.handler.EngineHandler`.
    """

    def __init__(
        self,
        config: RedSunSessionInfo,
        virtual_bus: HardwareVirtualBus,
        module_bus: ModuleVirtualBus,
        during_task: DuringTask,
    ) -> None:
        self._config = config
        self._virtual_bus = virtual_bus
        self._module_bus = module_bus
        self._plans: dict[str, dict[str, partial[MsgGenerator[Any]]]] = {}
        self._models: dict[str, ModelProtocol] = {}

        # TODO: there should be a way to pass
        #       custom metadata to the engine;
        #       the config should be enough
        # Bluesky's not fully typed;
        # so we need to ignore the type checking
        self._engine = RunEngine(during_task=during_task)  # type: ignore[no-untyped-call]

    def shutdown(self) -> None:
        """Invoke "stop" method on the run engine.

        "stop" marks it as successfull.
        """
        self._engine.stop()  # type: ignore[no-untyped-call]

    def register_plan(
        self, controller: str, name: str, plan: partial[MsgGenerator[Any]]
    ) -> None:
        """Register a workflow with the handler.

        Parameters
        ----------
        controller : str
            The name of the controller.
        name : str
            The name of the plan.
        plan : partial[MsgGenerator[Any]]
            The plan to register.
        """
        if controller not in self._plans.keys():
            self._plans[controller] = {name: plan}
        else:
            self._plans[controller][name] = plan

    def load_model(self, name: str, model: ModelProtocol) -> None:  # noqa: D102
        self._models[name] = model

    def subscribe(  # noqa: D102
        self,
        func: Callable[
            [Literal["all", "start", "descriptor", "event", "stop"], dict[str, Any]],
            None,
        ],
        name: Optional[Literal["all", "start", "descriptor", "event", "stop"]] = "all",
    ) -> int:
        return self._engine.subscribe(func, name)  # type: ignore

    def unsubscribe(self, token: int) -> None:  # noqa: D102
        return self._engine.unsubscribe(token)  # type: ignore

    def execute(self, controller: str, name: str) -> None:
        """Execute a plan.

        Parameters
        ----------
        controller : str
            The name of the controller.
        name : str
            The name of the plan.
        """
        try:
            self.debug(f"Executing plan {name} from controller {controller}")
            plan = self._plans[controller][name]
            self._engine(plan)
        except PlanHalt:
            self.debug(f"Plan {name} from controller {controller} halted")
            pass

    def halt(self) -> None:
        """Halt the current plan."""
        self._engine.halt()  # type: ignore[no-untyped-call]

    @property
    def engine(self) -> RunEngine:
        """Execution engine instance."""
        return self._engine

    @property
    def plans(self) -> dict[str, dict[str, partial[MsgGenerator[Any]]]]:
        """Plans dictionary."""
        return self._plans

    @property
    def models(self) -> dict[str, ModelProtocol]:
        """Model dictionary."""
        return self._models
