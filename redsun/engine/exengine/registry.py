from typing import TYPE_CHECKING
from redsun.engine.registry import DeviceRegistry

if TYPE_CHECKING:
    from typing import Dict, Union
    from redsun.config import RedSunInstanceInfo
    from redsun.toolkit.virtualbus import VirtualBus
    from redsun.toolkit.engine.exengine import (
        ExEngineDetectorModel,
        ExEngineMMCameraModel,
    )

__all__ = ['ExEngineRegistry']

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

    _detectors : "Dict[str, Union[ExEngineDetectorModel, ExEngineMMCameraModel]]" = {}

    def __init__(self, 
                config_options: "RedSunInstanceInfo",
                virtual_bus: "VirtualBus", 
                module_bus: "VirtualBus"):
        super().__init__(config_options, virtual_bus, module_bus)
    
    @property
    def detectors(self) -> "Dict[str, Union[ExEngineDetectorModel, ExEngineMMCameraModel]]":
        return self._detectors