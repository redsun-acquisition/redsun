from typing import TYPE_CHECKING
from abc import ABC, abstractmethod
from redsun.toolkit.config import PixelPhotometricTypes
from redsun.toolkit.utils import create_evented_model_info

if TYPE_CHECKING:
    from redsun.toolkit.config import DetectorModelInfo
    from typing import Tuple, Union

class DetectorModel(ABC):
    """ 
    `DetectorModel` abstract base class.

    The `DetectorModel` is the base class from which all detectors, regardless of the supported engine, must inherit.
    It provides the basic information about the detector model and the properties exposable to the upper layers for user interaction.

    It does **not** provide APIs for performing actions, which must be instead defined by the engine-specific detector classes.

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

        # base device information
        self._name = model_info.modelName
        self._modelParams = model_info.modelParams
        self._vendor = model_info.vendor
        self._serialNumber = model_info.serialNumber
        self._supportedEngines = model_info.supportedEngines

        # detector-specific information
        self._type = model_info.type
        self._sensorSize = model_info.sensorSize
        self._pixelSize = model_info.pixelSize
        self._exposureEGU = model_info.exposureEGU

        # user-defined information
        self._pixelPhotometric = pixel_photometric
        self._bitsPerPixel = bits_per_pixel
        self._binning = binning
        self._offset = offset
        if shape is None:
            self._shape = self._sensorSize
        else:
            self._shape = shape


    @property
    def name(self) -> str:
        return self._name

    @property
    def modelParams(self) -> dict:
        return self._modelParams

    @property
    def vendor(self) -> str:
        return self._vendor

    @property
    def serialNumber(self) -> str:
        return self._serialNumber

    @property
    def supportedEngines(self) -> list[str]:
        return self._supportedEngines

    @property
    def type(self) -> str:
        return self._type

    @property
    def sensorSize(self) -> Tuple[int, int]:
        return self._sensorSize

    @property
    def pixelSize(self) -> Tuple[float, float]:
        return self._pixelSize

    @property
    def exposureEGU(self) -> str:
        return self._exposureEGU

    @property
    def pixelPhotometric(self) -> list[PixelPhotometricTypes]:
        return self._pixelPhotometric

    @property
    def bitsPerPixel(self) -> set[int]:
        return self._bitsPerPixel
    
    @property
    def binning(self) -> list[int]:
        return self._binning

    @property
    def offset(self) -> Tuple[int, int]:
        return self._offset

    @property
    def shape(self) -> Tuple[int, int]:
        return self._shape


    
    