from pydantic.dataclasses import dataclass
from typing import Union, Dict, Optional, Tuple
from enum import Enum

class AcquisitionEngineTypes(str, Enum):
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

class DetectorModelTypes(str, Enum):
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

class PixelPhotometricTypes(str, Enum):
    """ Supported pixel photometric types.

    Parameters
    ----------
    GRAY : str
        Gray scale pixel.
    RGB : str
        RGB pixel.
    """

    GRAY : str = 'gray'
    RGB : str = 'rgb'

class MotorModelTypes(str, Enum):
    """ Supported motor types.

    Parameters
    ----------
    STEPPER : str
        Stepper motor.
    """
    STEPPER : str = 'stepper'

class LightModelTypes(str, Enum):
    """ Supported light source types.

    Parameters
    ----------
    LASER : str
        Laser light source.
    """
    LASER : str = 'laser'

class ScannerModelTypes(str, Enum):
    """ Supported scanner types.

    Parameters
    ----------
    GALVO : str
        Galvanometric scanner.
    """
    GALVO : str = 'galvo'

class ControllerTypes(str, Enum):
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

    Parameters
    ----------

    topology : ControllerTypes
        Controller topology. Defaults to 'device'.
    supportedEngines : list[AcquisitionEngineTypes]
        Supported acquisition engines list. Defaults to ['exengine'].
    """
    topology : ControllerTypes = ControllerTypes.DEVICE
    supportedEngines : list[AcquisitionEngineTypes] = [AcquisitionEngineTypes.EXENGINE]

@dataclass
class DeviceModelInfo:
    """ Base class for device model's information. 
    
    Parameters
    ----------
    modelName : str
        Device model name.
    modelParams : Dict[str, Union[str, int, float]]
        Device model parameters dictionary. Used to store start-up configuration parameters.
    supportedEngines : list[AcquisitionEngineTypes]
        Supported acquisition engines list. Defaults to ['exengine'].
    vendor : Optional[str]
        Detector vendor. Optional for debugging purposes. Defaults to 'N/A'.
    serialNumber : Optional[str]
        Detector serial number. Optional for debugging purposes. Defaults to 'N/A'.
    """
    modelName : str
    modelParams : Dict[str, Union[str, int, float]]
    supportedEngines : list[AcquisitionEngineTypes] = [AcquisitionEngineTypes.EXENGINE]
    vendor : Optional[str] = "N/A"
    serialNumber : Optional[str] = "N/A"
    

@dataclass
class DetectorModelInfo(DeviceModelInfo):
    """ Detector model informations. 
    
    Parameters
    ----------
    type : DetectorModelTypes
        Detector type. Currently supported values are
        'area', 'line' and 'point'. Defaults to 'area'.    
    sensorSize: Tuple[int]
        Detector sensor size in pixels: represents the 2D axis (Y, X). Only applicable
        for 'line' and 'area' detectors. Defaults to `(1024, 1024)`.
    pixelSize : Tuple[float]
        Detector pixel size in micrometers: represents the 3D axis (Z, Y, X).
        Defaults to `(1, 1, 1)`.
    exposureEGU : str
        Engineering unit for exposure time, e.g. 'ms', 'μs'. Defaults to 'ms'.
    """
    type : str = DetectorModelTypes.AREA
    sensorSize: Tuple[int, int] = (1024, 1024)
    pixelSize : Tuple[float, float, float] = (1, 1, 1)
    exposureEGU : str = 'ms'


@dataclass
class LightModelInfo(DeviceModelInfo):
    """ Light source model informations.

    Parameters
    ----------
    type : LightModelTypes
        Light source type. Defaults to 'laser'.
    wavelength : int
        Light source wavelength in nanometers.
    powerEGU : str
        Engineering unit for light source, .e.g. 'mW', 'μW'. Defaults to 'mW'.
    minPower : Union[float, int]
        Minimum light source power. Defaults to 0.
    maxPower : Union[float, int]
        Maximum light source power.
    powerStep: Union[float, int]
        Power increase/decrease minimum step size.
    """
    type : LightModelTypes = LightModelTypes.LASER
    wavelength : int
    powerEGU : str = 'mW'
    minPower : Union[float, int] = 0
    maxPower : Union[float, int]
    powerStep: Union[float, int]

@dataclass
class MotorModelInfo(DeviceModelInfo):
    """ Motor model informations.

    Parameters
    ----------

    type : MotorModelTypes
        Motor type. Defaults to 'stepper'.
    stepEGU : str
        Engineering unit for steps, e.g. 'mm', 'μm'. Defaults to 'μm'.
    axes : list[str]
        Supported motor axes. Suggestion is to be a list of
        single character, capital strings, e.g. ['X', 'Y', 'Z'].
    returnHome : bool
        If `True`, motor will return to home position
        (defined as  the initial position the motor had at RedSun's startup)
        after RedSun is closed. Defaults to `False`.
    """

    type : str = MotorModelTypes.STEPPER
    stepEGU : str = 'μm'
    axes : list[str]
    returnHome : bool = False

@dataclass
class ScannerModelInfo(DeviceModelInfo):
    """ Scanner model informations.

    Parameters
    ----------

    type : ScannerModelTypes
        Scanner type. Defaults to 'galvo'.
    axes : list[str]
        Supported scanner axes. Suggestion is to be a list of
        single character, capital strings, e.g. ['X', 'Y', 'Z'].
    """
    type : ScannerModelTypes = ScannerModelTypes.GALVO
    axes : list[str]
    # TODO: investigate what other parameters are needed for scanner