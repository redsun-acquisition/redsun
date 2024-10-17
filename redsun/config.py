from pydantic.dataclasses import dataclass
from pydantic import Field
from redsun.toolkit.config import (
        DetectorModelInfo,
        LightModelInfo,
        MotorModelInfo,
        ScannerModelInfo,
        AcquisitionEngineTypes
    )
from typing import Dict, Optional


@dataclass
class RedSunInstanceInfo:
    """ RedSun instance configuration class.

    This class is used to store the configuration of a running RedSun application;
    it provides information about the hardware layout and the selected acquisition engine.
    All hardware models must be coherent with the selected acquisition engine.

    A minimal configuration should include the selected acquisition engine.

    Attributes
    ----------
    engine : AcquisitionEngineTypes
        Acquisition engine selected for the current instance.
        Defaults to 'exengine'.
    detectors : Optional[Dict[str, DetectorModelInfo]]
        Detector model informations dictionary.
        Defaults to an empty dictionary.
    lights : Optional[Dict[str, LightModelInfo]]
        Light source model informations dictionary.
        Defaults to an empty dictionary.
    motors : Optional[Dict[str, MotorModelInfo]]
        Motor model informations dictionary.
        Defaults to an empty dictionary.
    scanners : Optional[Dict[str, ScannerModelInfo]]
        Scanner model informations dictionary.
        Defaults to an empty dictionary.
    """
    engine : "AcquisitionEngineTypes" = AcquisitionEngineTypes.EXENGINE
    detectors : "Optional[Dict[str, DetectorModelInfo]]" = Field(default_factory=dict)
    lights : "Optional[Dict[str, LightModelInfo]]" = Field(default_factory=dict)
    motors : "Optional[Dict[str, MotorModelInfo]]" = Field(default_factory=dict)
    scanners : "Optional[Dict[str, ScannerModelInfo]]" = Field(default_factory=dict)