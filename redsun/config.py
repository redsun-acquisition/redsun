from pydantic.dataclasses import dataclass
from typing import Dict, Optional
from redsun.toolkit.config import (
    DetectorModelInfo,
    LightModelInfo,
    MotorModelInfo,
    ScannerModelInfo,
    AcquisitionEngineTypesEnum,
)

@dataclass
class RedSunInstanceInfo:
    """ RedSun instance configuration class.

    This class is used to store the configuration of a running RedSun application;
    it provides information about the hardware layout and the selected acquisition engine.
    All hardware models must be coherent with the selected acquisition engine.
    """

    engine : Optional[str] = AcquisitionEngineTypesEnum.EXENGINE
    """ Acquisition engine selected for the current instance.
    Defaults to 'exengine'.
    """

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