"""ExEngine handler class."""

from typing import TYPE_CHECKING, Union, TypeAlias

from exengine import ExecutionEngine
from sunflare.engine import DetectorModel, EngineHandler, MotorModel
from sunflare.errors import UnsupportedDeviceType

if TYPE_CHECKING:
    from typing import Any

    from sunflare.config import RedSunInstanceInfo
    from sunflare.engine.exengine import (
        ExEngineDetectorModel,
        ExEngineDoubleMotorModel,
        ExEngineMMCameraModel,
        ExEngineMMDoubleMotorModel,
        ExEngineMMSingleMotorModel,
        ExEngineSingleMotorModel,
    )
    from sunflare.virtualbus import VirtualBus

DetectorModels: TypeAlias = Union["ExEngineDetectorModel", "ExEngineMMCameraModel"]
MotorModels: TypeAlias = Union[
    "ExEngineSingleMotorModel",
    "ExEngineDoubleMotorModel",
    "ExEngineMMSingleMotorModel",
    "ExEngineMMDoubleMotorModel",
]


class ExEngineHandler(EngineHandler):
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

    _detectors: "dict[str, DetectorModels]" = {}
    _motors: "dict[str, MotorModels]" = {}

    def __init__(
        self,
        config_options: "RedSunInstanceInfo",
        virtual_bus: "VirtualBus",
        module_bus: "VirtualBus",
    ):
        super().__init__(config_options, virtual_bus, module_bus)
        self._engine = ExecutionEngine()

    def register_device(  # noqa: D102
        self, name: str, device: Union[MotorModels, DetectorModels]
    ) -> None:
        if isinstance(device, DetectorModel):
            self._detectors[name] = device
        elif isinstance(device, MotorModel):
            self._motors[name] = device
        else:
            raise ValueError(
                f"Device of type {type(device)} not supported by ExEngine."
            )

    def shutdown(self) -> None:  # noqa: D102
        self._engine.shutdown()

    @property
    def detectors(self) -> "dict[str, DetectorModels]":
        """Dictionary containing all the registered ExEngine detectors."""
        return self._detectors

    @property
    def motors(self) -> "dict[str, MotorModels]":
        """Dictionary containing all the registered ExEngine motors."""
        return self._motors

    @property
    def engine(self) -> ExecutionEngine:
        """Execution engine instance."""
        return self._engine

    @property
    def lights(self) -> "dict[str, Any]":
        """Dictionary containing all the registered ExEngine light sources."""
        raise UnsupportedDeviceType("ExEngine", "Light")

    @property
    def scanners(self) -> "dict[str, Any]":
        """Dictionary containing all the registered ExEngine scanners."""
        raise UnsupportedDeviceType("ExEngine", "Scanner")
