from pydantic.dataclasses import dataclass
from typing import Union, Dict, Optional
from enum import Enum

class DetectorModelTypesEnum:
    AREA : str = 'area'
    LINE : str = 'line'
    POINT : str = 'point'

class MotorModelTypesEnum:
    STEPPER : str = 'stepper'

class ScannerModelTypesEnum:
    GALVO : str = 'galvo'

class ControllerTypesEnum:
    DEVICE : str = 'device'
    COMPUTATIONAL : str = 'computational'

@dataclass(frozen=True)
class ControllerInfo:
    """ Controller information class.
    """

    topology : str = ControllerTypesEnum.DEVICE
    """
    Controller topology. Currently supported values are
    'device' and 'computational'.
    """

@dataclass(frozen=True)
class DeviceModelInfo:
    """ Base class for device model's information. """

    modelName : str
    """ Device model name
    """

    modelParameters : Dict[str, Union[str, int, float]]
    """ Device model parameters dictionary. Used to store
    start-up configuration parameters.
    """

    vendor : Optional[str] = None
    """ Detector vendor. Optional for debugging purposes. 
    """

    serialNumber : Optional[str] = None
    """ Detector serial number. Optional for debugging purposes.
    """

@dataclass(frozen=True)
class DetectorModelInfo(DeviceModelInfo):
    """ Detector model informations. """

    type : str = DetectorModelTypesEnum.AREA
    """ Detector type. Currently supported values are
    'area', 'line' and 'point'.
    """

    pixelSize : float
    """ Detector pixel size in micrometers. If unknown, set to `None`.
    """

@dataclass(frozen=True)
class LightModelInfo(DeviceModelInfo):
    """ Light source model informations.
    """

    type : str = 'laser'
    """ Light source type. Currently supported values are
    'laser'.
    """

    wavelength : int
    """ Light source wavelength in nanometers.
    """

    egu : str
    """ Engineering unit for light source, .e.g. 'mW', 'W'.
    """

    minPower : Union[float, int]
    """ Minimum light source power.
    """

    maxPower : Union[float, int]
    """ Maximum light source power. 
    """

    powerStep: Union[float, int]
    """ Power increase/decrease step size.
    """

@dataclass(frozen=True)
class MotorModelInfo(DeviceModelInfo):
    """ Motor model informations.
    """

    type : str = MotorModelTypesEnum.STEPPER
    """ Motor type. Currently supported values are
    'stepper'.
    """

    egu : str = 'μm'
    """ Engineering unit for motor, e.g. 'mm', 'um'.
    Defaults to 'μm'.
    """

    axes : list
    """ Supported motor axes. Suggestion is to be a list of
    single character, capital strings, e.g. ['X', 'Y', 'Z'].
    """

    returnHome : bool = False
    """ If `True`, motor will return to home position
    (defined as  the initial position the motor had at RedSun's startup)
    after RedSun is closed. Defaults to `False`.
    """

@dataclass(frozen=True)
class ScannerModelInfo(DeviceModelInfo):
    """ Scanner model informations.
    """

    type : str = ScannerModelTypesEnum.GALVO
    """ Scanner type. Currently supported values are
    'galvo'.
    """

    axes : list
    """ Supported scanner axes. Preferred to be a list of
    single character, capital strings, e.g. ['X', 'Y', 'Z'].
    """

@dataclass
class RedSunInstance:
    detectors : Dict[str, DetectorModelInfo]
    """ Detector model informations dictionary.
    """

    lights : Dict[str, LightModelInfo]
    """ Light source model informations dictionary.
    """

    motors : Dict[str, MotorModelInfo]
    """ Motor model informations dictionary.
    """

    scanners : Dict[str, ScannerModelInfo]
    """ Scanner model informations dictionary.
    """

    def add_plugin_info(self, plugin_name: str, plugin_info: DeviceModelInfo):
        """ Add plugin information to the corresponding dictionary.
        """

        # TODO: to implement
        
        ...