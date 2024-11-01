from typing import TYPE_CHECKING, Union

from exengine import ExecutionEngine
from redsun.toolkit.engine import DetectorModel, EngineHandler, MotorModel
from redsun.toolkit.errors import UnsupportedDeviceType

if TYPE_CHECKING:
    from typing import Any, Dict

    from redsun.toolkit.config import RedSunInstanceInfo
    from redsun.toolkit.engine.exengine import (
        ExEngineDetectorModel,
        ExEngineDoubleMotorModel,
        ExEngineMMCameraModel,
        ExEngineMMDoubleMotorModel,
        ExEngineMMSingleMotorModel,
        ExEngineSingleMotorModel,
    )
    from redsun.toolkit.virtualbus import VirtualBus

DetectorModels = Union["ExEngineDetectorModel", "ExEngineMMCameraModel"]
MotorModels = Union[
    "ExEngineSingleMotorModel",
    "ExEngineDoubleMotorModel",
    "ExEngineMMSingleMotorModel",
    "ExEngineMMDoubleMotorModel",
]


class ExEngineHandler(EngineHandler):
    """ ExEngine handler class.

    All models compatible with ExEngine are registered here at application startup.

    Parameters
    ----------
    config_options : RedSunInstanceInfo
        Configuration options for the RedSun instance.
    virtual_bus : VirtualBus
        The virtual bus instance for the RedSun instance.
    module_bus : VirtualBus
        The virtual bus instance for the module.
    
    Properties
    ----------
    detectors : `Dict[str, Union[ExEngineDetectorModel, ExEngineMMCameraModel]]` \\
        Dictionary containing all the registered ExEngine detectors.
    motors : `Dict[str, Union[ExEngineSingleMotorModel, ExEngineDoubleMotorModel, ExEngineMMSingleMotorModel, ExEngineMMDoubleMotorModel]]` \\
        Dictionary containing all the registered ExEngine motors.
    """

    _detectors: "Dict[str, DetectorModels]" = {}
    _motors: "Dict[str, MotorModels]" = {}

    def __init__(
        self,
        config_options: "RedSunInstanceInfo",
        virtual_bus: "VirtualBus",
        module_bus: "VirtualBus",
    ):
        super().__init__(config_options, virtual_bus, module_bus)
        self._engine = ExecutionEngine()

    def register_device(
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

    def shutdown(self) -> None:
        self._engine.shutdown()

    @property
    def detectors(self) -> "Dict[str, DetectorModels]":
        return self._detectors

    @property
    def motors(self) -> "Dict[str, MotorModels]":
        return self._motors

    @property
    def engine(self) -> ExecutionEngine:
        return self._engine

    @property
    def lights(self) -> "Dict[str, Any]":
        raise UnsupportedDeviceType("ExEngine", "Light")

    @property
    def scanners(self) -> "Dict[str, Any]":
        raise UnsupportedDeviceType("ExEngine", "Scanner")
