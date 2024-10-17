from abc import ABC, abstractmethod
from dataclasses import asdict
from typing import TYPE_CHECKING
from redsun.toolkit.utils import create_evented_dataclass
from redsun.toolkit.log import Loggable

if TYPE_CHECKING:
    from typing import Union
    from redsun.toolkit.config import (
        LightModelInfo,
        LightModelTypes
    )

__all__ = ['LightModel']

class LightModel(ABC, Loggable):

    """ 
    `LightModel` abstract base class.

    The `LightModel` is the base class from which all light sources, regardless of the supported engine, must inherit.
    It provides the basic information about the light source model and the properties exposable to the upper layers for user interaction.

    It does **not** provide APIs for performing actions, which must be instead defined by the engine-specific light source classes.

    The `LightModel` contains an extended, evented dataclass that allows the user to expose new properties to the upper layers using `psygnal`.

    Parameters
    ----------
    name: str
        - Light source instance unique identifier name.
        - User defined.
    model_info: LightModelInfo
        - Light source model information dataclass.
        - Provided by RedSun configuration.
    
    Properties
    ----------

    """
    @abstractmethod
    def __init__(self,
                 name : str,
                 model_info: "LightModelInfo") -> None:
        FullModelInfo = create_evented_dataclass(cls_name=model_info.modelName + "Info",
                                                    original_cls=type(model_info),
                                                    types={"name" : str},
                                                    values={"name" : name})
        self._modelInfo = FullModelInfo(**asdict(model_info))
    
    @property
    def name(self) -> str:
        return self._modelInfo.name

    @property
    def modelName(self) -> str:
        return self._modelInfo.modelName

    @property
    def modelParams(self) -> dict:
        return self._modelInfo.modelParams

    @property
    def vendor(self) -> str:
        return self._modelInfo.vendor
    
    @property
    def serialNumber(self) -> str:
        return self._modelInfo.serialNumber
    
    @property
    def supportedEngines(self) -> list:
        return self._modelInfo.supportedEngines
    
    @property
    def category(self) -> "LightModelTypes":
        return self._modelInfo.category
    
    @property
    def wavelength(self) -> int:
        return self._modelInfo.wavelength

    @property
    def powerEGU(self) -> str:
        return self._modelInfo.powerEGU

    @property
    def minPower(self) -> Union[float, int]:
        return self._modelInfo.minPower
    
    @property
    def maxPower(self) -> Union[float, int]:
        return self._modelInfo.maxPower
    
    @property
    def powerStep(self) -> Union[float, int]:
        return self._modelInfo.powerStep