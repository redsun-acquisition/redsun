from typing import TYPE_CHECKING
from abc import ABC, abstractmethod
from dataclasses import asdict
from redsun.toolkit.utils import create_evented_model_info
from redsun.toolkit.config import (
    DetectorModelInfo,
    PixelPhotometricTypes
)

if TYPE_CHECKING:
    from typing import Tuple, Union

class DetectorModel(ABC):
    """ 
    `DetectorModel` abstract base class.

    The `DetectorModel` is the base class from which all detectors, regardless of the supported engine, must inherit.
    It provides the basic information about the detector model and the properties exposable to the upper layers for user interaction.

    It does **not** provide APIs for performing actions, which must be instead defined by the engine-specific detector classes.

    The `DetectorModel` contains an extended, evented dataclass that allows the user to expose new properties to the upper layers using `psygnal`.

    Parameters
    ----------
    model_info: DetectorModelInfo
        - Detector model information dataclass.
        - Provided by RedSun configuration.
    exposure: Union[int, float]
        - Detector exposure time at startup (time scale defined by `exposureEGU`).
        - User defined.
    pixel_photometric: list[PixelPhotometricTypes]
        - List of supported pixel colors.
        - User defined.
        - Defaults to `[PixelPhotometricTypes.GRAY]`.
    bits_per_pixel: set[int]
        - Set of supported values for pixel width in bits.
        - User defined.
        - Defaults to `{8}`.
    offset: Tuple[int, int]
        - Detector offset at startup (Y, X).
        - User-defined.
        - Only applicable for 'line' and 'area' detectors. Defaults to `(0, 0)`.
    shape: Tuple[int, int]
        - Detector shape at startup (Y, X). 
        - User-defined. 
        - If set to `None`, it defaults to the sensor size. 
        - Only applicable for 'line' and 'area' detectors. Defaults to `None`.
    
    Properties
    ----------
    name: str
        - Detector model name.
    modelParams: dict
        - Detector model parameters dictionary.
    vendor: str
        - Detector vendor.
    serialNumber: str
        - Detector serial number.       
    supportedEngines: list[AcquisitionEngineTypes]
        - Supported acquisition engines list.
    type: DetectorModelTypes
        - Detector type.
    sensorSize: Tuple[int, int]
        - Detector sensor size in pixels: represents the 2D axis (Y, X). Only applicable for 'line' and 'area' detectors.
    pixelSize: Tuple[float, float]
        - Detector pixel size in micrometers: represents the 3D axis (Z, Y, X).
    exposureEGU: str
        - Detector exposure unit.
    pixelPhotometric: list[PixelPhotometricTypes]
        - List of supported pixel colors.
    bitsPerPixel: set[int]
        - Set of supported values for pixel width in bits.
    binning: list[int]
        - List of supported binning values.
    offset: Tuple[int, int]
        - Detector offset (Y, X). Only applicable for 'line' and 'area' detectors.
    shape: Tuple[int, int]
        - Detector shape (Y, X). Only applicable for 'line' and 'area' detectors.
    """

    @abstractmethod
    def __init__(self, model_info: "DetectorModelInfo",
                exposure: "Union[int, float]",
                pixel_photometric: "list[PixelPhotometricTypes]" = [PixelPhotometricTypes.GRAY],
                bits_per_pixel: "set[int]" = {8},
                binning : "list[int]" = [1],
                offset: "Tuple[int, int]" = (0, 0),
                shape: "Tuple[int, int]" = None,) -> None:

        cls_name = model_info.modelName + "Info"
        types = {
            "pixelPhotometric" : PixelPhotometricTypes,
            "bitsPerPixel" : int,
            "binning" : int,
            "offset" : Tuple[int, int],
            "shape" : Tuple[int, int]
        }
        values = {
            "pixelPhotometric" : pixel_photometric,
            "bitsPerPixel" : bits_per_pixel,
            "binning" : binning,
            "offset" : offset,
            "shape" : shape if shape is not None else model_info.sensorSize
        }
        FullModelInfo = create_evented_model_info(cls_name=cls_name,
                                                  original_cls=DetectorModelInfo,
                                                  types=types,
                                                  values=values)
        
        self._modelInfo = FullModelInfo(**asdict(model_info).update(values))

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
    def supportedEngines(self) -> list[str]:
        return self._modelInfo.supportedEngines

    @property
    def type(self) -> str:
        return self._modelInfo.type

    @property
    def sensorSize(self) -> Tuple[int, int]:
        return self._modelInfo.sensorSize

    @property
    def pixelSize(self) -> Tuple[float, float]:
        return self._modelInfo.pixelSize

    @property
    def exposureEGU(self) -> str:
        return self._modelInfo.exposureEGU

    @property
    def pixelPhotometric(self) -> list[PixelPhotometricTypes]:
        return self._modelInfo.pixelPhotometric

    @property
    def bitsPerPixel(self) -> set[int]:
        return self._modelInfo.bitsPerPixel
    
    @property
    def binning(self) -> list[int]:
        return self._modelInfo.binning

    @property
    def offset(self) -> Tuple[int, int]:
        return self._modelInfo.offset

    @property
    def shape(self) -> Tuple[int, int]:
        return self._modelInfo.shape


    
    