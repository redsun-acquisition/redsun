from pydantic.dataclasses import dataclass
from pydantic import Field
from typing import Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from redsun.toolkit.config import (
        DetectorModelInfo,
        LightModelInfo,
        MotorModelInfo,
        ScannerModelInfo,
        AcquisitionEngineTypes
    )


@dataclass
class RedSunInstanceInfo:
    """ RedSun instance configuration class.

    This class is used to store the configuration of a running RedSun application;
    it provides information about the hardware layout and the selected acquisition engine.
    All hardware models must be coherent with the selected acquisition engine.

    A minimal configuration should include the selected acquisition engine.
    """

    engine : "AcquisitionEngineTypes" = 'exengine'
    """ Acquisition engine selected for the current instance.
    Defaults to 'exengine'.
    """

    detectors : Optional[Dict[str, DetectorModelInfo]] = Field(default_factory=dict)
    """ Detector model informations dictionary.
    Defaults to None.
    """

    lights : Optional[Dict[str, LightModelInfo]] = Field(default_factory=dict)
    """ Light source model informations dictionary.
    Defaults to None.
    """

    motors : Optional[Dict[str, MotorModelInfo]] = Field(default_factory=dict)
    """ Motor model informations dictionary.
    Defaults to None.
    """

    scanners : Optional[Dict[str, ScannerModelInfo]] = Field(default_factory=dict)
    """ Scanner model informations dictionary.
    Defaults to None.
    """