from pydantic.dataclasses import dataclass
from typing import Union, Dict, Optional
from enum import Enum

class AcquisitionEngineTypesEnum(Enum):
    """ Supported acquisition engine entities.

    Acquisition engines are singleton objects that are instantiated within RedSun and operate
    as workflow managers for the acquisition process. They are responsible for the orchestration
    of the different hardware components currently loaded in RedSun. Accross the entire
    module there can be only one active acquisition engine at a time, otherwise RedSun will 
    raise an exception.

    Parameters
    ----------
    EXENGINE : str
        ExEngine: execution engine for microscopy control.\\
        For more informations, refer to the `ExEngine documentation page<https://exengine.readthedocs.io/en/latest/index.html>`_
    """
    EXENGINE : str = 'exengine'

class DetectorModelTypesEnum(Enum):
    """ Supported detector types.
    
    Detectors are devices that are used to capture images or signals from the sample.

    Parameters
    ----------
    AREA : str
        Area detector (i.e. CCD, CMOS cameras).
    LINE : str
        Line detector (i.e. photodiode arrays).
    POINT : str
        Point detector (i.e. Avalanche Photodiode (APD) detector).
    """

    AREA : str = 'area'
    LINE : str = 'line'
    POINT : str = 'point'

class MotorModelTypesEnum(Enum):
    """ Supported motor types.

    Parameters
    ----------
    STEPPER : str
        Stepper motor.
    """
    STEPPER : str = 'stepper'

class ScannerModelTypesEnum(Enum):
    """ Supported scanner types.

    Parameters
    ----------
    GALVO : str
        Galvanometric scanner.
    """
    GALVO : str = 'galvo'

class ControllerTypesEnum(Enum):
    """ Supported controller topology types.

    Parameters
    ----------
    DEVICE : str
        Device controllers are used to expose lower hardware devices of the same type (e.g. motors, detectors, etc.) with a unique interface to facilitate
        the interaction with the acquisition engine and the upper layers. They do not provide computational capabilities other than the ones needed to interact with
        the hardware (i.e. compute motor steps or update detector exposure time).
    COMPUTATIONAL : str
        Computational controllers provide computational resources or define workflows that are independent of specific hardware devices and can inform
        the acquisition engine of a new workflow that can be injected into the acquisition process.
    """

    DEVICE : str = 'device'
    COMPUTATIONAL : str = 'computational'

@dataclass
class ControllerInfo:
    """ Controller information class.
    """

    topology : str = ControllerTypesEnum.DEVICE
    """
    Controller topology. Currently supported values are
    'device' and 'computational'.
    """

    supportedEngines : list = [
        AcquisitionEngineTypesEnum.EXENGINE
    ]
    """ Supported acquisition engines list.
    Defaults to ['exengine'].
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

    supportedEngines : list = [
        AcquisitionEngineTypesEnum.EXENGINE
    ]
    """ Supported acquisition engines list. Defaults to ['exengine'].
    """

@dataclass(frozen=True)
class DetectorModelInfo(DeviceModelInfo):
    """ Detector model informations. """

    type : str = DetectorModelTypesEnum.AREA
    """ Detector type. Currently supported values are
    'area', 'line' and 'point'.
    """

    pixelSize : float = None
    """ Detector pixel size in micrometers. If unknown, set to `None`.
    Defaults to `None`.
    """

    exposureEGU : str = 'ms'
    """ Engineering unit for exposure time, e.g. 'ms', 'μs'. 
    Defaults to 'ms'.
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

    powerEGU : str = 'mW'
    """ Engineering unit for light source, .e.g. 'mW', 'μW'.
    Defaults to 'mW'.
    """

    minPower : Union[float, int] = 0
    """ Minimum light source power.
    Defaults to 0.
    """

    maxPower : Union[float, int]
    """ Maximum light source power. 
    """

    powerStep: Union[float, int]
    """ Power increase/decrease minimum step size.
    """

@dataclass(frozen=True)
class MotorModelInfo(DeviceModelInfo):
    """ Motor model informations.
    """

    type : str = MotorModelTypesEnum.STEPPER
    """ Motor type. Currently supported values are
    'stepper'.
    """

    motorEGU : str = 'μm'
    """ Engineering unit for motor, e.g. 'mm', 'μm'.
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