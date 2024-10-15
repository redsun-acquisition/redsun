from typing import TYPE_CHECKING, Union
from redsun.engine.registry import DeviceRegistry
from redsun.toolkit.engine import (
    DetectorModel,
    MotorModel
)

if TYPE_CHECKING:
    from typing import Dict
    from redsun.config import RedSunInstanceInfo
    from redsun.toolkit.virtualbus import VirtualBus
    from redsun.toolkit.engine.exengine import (
        ExEngineDetectorModel,
        ExEngineMMCameraModel,
        ExEngineSingleMotorModel,
        ExEngineDoubleMotorModel,
        ExEngineMMSingleMotorModel,
        ExEngineMMDoubleMotorModel
    )

__all__ = ['ExEngineRegistry']

DetectorModels = Union["ExEngineDetectorModel", "ExEngineMMCameraModel"]
MotorModels = Union["ExEngineSingleMotorModel", "ExEngineDoubleMotorModel", "ExEngineMMSingleMotorModel", "ExEngineMMDoubleMotorModel"]

class ExEngineRegistry(DeviceRegistry):
    """ ExEngine device registry class.

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

    detectors : Dict[str, Union[ExEngineDetectorModel, ExEngineMMCameraModel]]
        Dictionary containing all the registered ExEngine detectors.
    """

    _detectors : "Dict[str, DetectorModels]" = {}
    _motors : "Dict[str, MotorModels]" = {}

    def __init__(self, 
                config_options: "RedSunInstanceInfo",
                virtual_bus: "VirtualBus", 
                module_bus: "VirtualBus"):
        super().__init__(config_options, virtual_bus, module_bus)
    
    def register_device(self, name: str, device: Union[MotorModels, DetectorModels]) -> None:
        if isinstance(device, DetectorModel):
            self._detectors[name] = device
        elif isinstance(device, MotorModel):
            self._motors[name] = device
        else:
            raise ValueError(f"Device of type {type(device)} not supported by ExEngine.")
    
    @property
    def detectors(self) -> "Dict[str, DetectorModels]":
        return self._detectors
    
    @property
    def motors(self) -> "Dict[str, MotorModels]":
        return self._motors