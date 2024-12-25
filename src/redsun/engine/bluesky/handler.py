"""Module implementing the handler for the standard Bluesky engine."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Literal, Optional, Union, final

from sunflare.config import DetectorModelInfo, MotorModelInfo, RedSunInstanceInfo
from sunflare.engine import DetectorModel, EngineHandler, MotorModel
from sunflare.log import Loggable

from bluesky.run_engine import RunEngine

if TYPE_CHECKING:
    from sunflare.virtualbus import VirtualBus

    from bluesky.utils import DuringTask, MsgGenerator

Motor = MotorModel[MotorModelInfo]
Detector = DetectorModel[DetectorModelInfo]


@final
class BlueskyHandler(EngineHandler, Loggable):
    """
    Bluesky handler class.

    Parameters
    ----------
    config : RedSunInstanceInfo
        Configuration options for the RedSun instance.
    virtual_bus : VirtualBus
        The virtual bus instance for the RedSun instance.
    module_bus : VirtualBus
        The virtual bus instance for the module.
    during_task : DuringTask
        The DuringTask object. For more information,
        see :class:`~sunflare.engine.handler.EngineHandler`.
    """

    def __init__(
        self,
        config: RedSunInstanceInfo,
        virtual_bus: VirtualBus,
        module_bus: VirtualBus,
        during_task: DuringTask,
    ) -> None:
        self._config = config
        self._virtual_bus = virtual_bus
        self._module_bus = module_bus
        self._plans: dict[str, MsgGenerator[Any]] = {}
        self._motors: dict[str, Motor] = {}
        self._detectors: dict[str, Detector] = {}

        # TODO: there should be a way to pass
        #       custom metadata to the engine via
        #       either the config or the constructor
        self._engine = RunEngine(during_task=during_task)  # type: ignore[no-untyped-call]

    def shutdown(self) -> None:
        """Invoke "stop" method on the run engine.

        "stop" marks it as successfull.
        """
        self._engine.stop()  # type: ignore[no-untyped-call]

    def register_plan(self, name: str, plan: MsgGenerator[Any]) -> None:
        """Register a workflow with the handler."""
        if name not in self._plans.keys():
            self._plans[name] = plan
        else:
            self.error(f"Workflow {name} already registered. Aborted.")

    def load_device(self, name: str, device: Union[Motor, Detector]) -> None:  # noqa: D102
        if isinstance(device, MotorModel):
            self._motors[name] = device
        elif isinstance(device, DetectorModel):
            self._detectors[name] = device
        else:
            raise ValueError(f"Invalid device type: {type(device)}")

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

    @property
    def engine(self) -> RunEngine:
        """Execution engine instance."""
        return self._engine

    @property
    def plans(self) -> dict[str, MsgGenerator[Any]]:
        """Workflow dictionary."""
        return self._plans

    @property
    def detectors(self) -> dict[str, Detector]:
        """Detectors dictionary."""
        return self._detectors

    @property
    def motors(self) -> dict[str, Motor]:
        """Motors dictionary."""
        return self._motors
