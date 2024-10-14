from abc import ABC, abstractmethod
from psygnal import evented
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from redsun.toolkit.config import MotorModelInfo

class MotorModel(ABC):
    """
    `MotorModel` abstract base class.

    The `MotorModel` is the base class from which all detectors, regardless of the supported engine, must inherit.
    It provides the basic information about the detector model and the properties exposable to the upper layers for user interaction.

    It does **not** provide APIs for performing actions, which must be instead defined by the engine-specific detector classes.

    The `MotorModel` contains an extended, evented dataclass that allows the user to expose new properties to the upper layers using `psygnal`.

    Parameters
    ----------
    model_info: MotorModelInfo
        - Motor model information dataclass.
        - Provided by RedSun configuration.
    
    Properties
    ----------
    name: str
        - Motor model name.
    modelParams: dict
        - Motor model parameters dictionary.
    vendor: str
        - Motor vendor.
    serialNumber: str
        - Motor serial number.       
    supportedEngines: list[AcquisitionEngineTypes]
        - Supported acquisition engines list.
    category: DetectorModelTypes
        - Motor type.
    stepEGU: str
        - Motor step unit.
    stepSize: float
        - Motor step size.
    axes : list[str]
        - Motor axes.
    returnHome : bool
        If `True`, motor will return to home position
        (defined as  the initial position the motor had at RedSun's startup)
        after RedSun is closed. Defaults to `False`.
    """
    @abstractmethod
    def __init__(self,
                model_info: "MotorModelInfo",):
        self._modelInfo = evented(model_info)
    
    @property
    def name(self) -> str:
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
    def category(self) -> str:
        return self._modelInfo.category
    
    @property
    def stepEGU(self) -> str:
        return self._modelInfo.stepEGU
    
    @property
    def stepSize(self) -> float:
        return self._modelInfo.stepSize
    
    @property
    def axes(self) -> list:
        return self._modelInfo.axes

    @property
    def returnHome(self) -> bool:
        return self._modelInfo.returnHome
