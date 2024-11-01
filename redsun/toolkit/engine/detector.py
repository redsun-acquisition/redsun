from abc import ABC, abstractmethod
from dataclasses import asdict
from typing import TYPE_CHECKING

from redsun.toolkit.config import PixelPhotometricTypes
from redsun.toolkit.log import Loggable
from redsun.toolkit.utils import create_evented_dataclass

if TYPE_CHECKING:
    from typing import Any, Dict, List, Optional, Set, Tuple, Union

    from redsun.toolkit.config import AcquisitionEngineTypes, DetectorModelInfo


class DetectorModel(ABC, Loggable):
    """
    `DetectorModel` abstract base class. Implements `Loggable` protocol.

    The `DetectorModel` is the base class from which all detectors, regardless of the supported engine, must inherit.
    It provides the basic information about the detector model and the properties exposable to the upper layers for user interaction.

    It does **not** provide APIs for performing actions, which must be instead defined by the engine-specific detector classes.

    The `DetectorModel` contains an extended, evented dataclass that allows the user to expose new properties to the upper layers using `psygnal`.

    Parameters
    ----------
    name: str
        - Detector instance unique identifier name.
        - User defined.
    model_info: DetectorModelInfo
        - Detector model information dataclass.
        - Provided by RedSun configuration.
    exposure: Union[int, float]
        - Detector exposure time at startup (time scale defined by `exposureEGU`).
        - User defined.
    pixel_photometric: list[PixelPhotometricTypes]
        - List of supported pixel colors.
        - User defined.
        - Defaults to `gray`.
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
        - Detector instance unique identifier name.
    modelName: str
        - Detector model name.
    modelParams: dict
        - Detector model parameters dictionary.
    vendor: str
        - Detector vendor.
    serialNumber: str
        - Detector serial number.
    supportedEngines: list[AcquisitionEngineTypes]
        - Supported acquisition engines list.
    category: DetectorModelTypes
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
    def __init__(
        self,
        name: "str",
        model_info: "DetectorModelInfo",
        exposure: "Union[int, float]",
        pixel_photometric: "Optional[list[PixelPhotometricTypes]]" = [
            PixelPhotometricTypes.GRAY
        ],
        bits_per_pixel: "Optional[set[int]]" = {8},
        binning: "Optional[list[int]]" = [1],
        offset: "Optional[Tuple[int, int]]" = (0, 0),
        shape: "Optional[Tuple[int, int]]" = None,
    ) -> None:
        cls_name = model_info.modelName + "Info"
        types = {
            "name": str,
            "pixelPhotometric": PixelPhotometricTypes,
            "bitsPerPixel": int,
            "binning": int,
            "offset": Tuple[int, int],
            "shape": Tuple[int, int],
        }
        values = {
            "pixelPhotometric": pixel_photometric,
            "bitsPerPixel": bits_per_pixel,
            "binning": binning,
            "offset": offset,
            "shape": shape if shape is not None else model_info.sensorSize,
        }
        FullModelInfo = create_evented_dataclass(
            cls_name=cls_name, original_cls=type(model_info), types=types, values=values
        )

        model_info_dict = asdict(model_info)
        model_info_dict.update(values)
        self._modelInfo = FullModelInfo(**model_info_dict)

    @property
    def name(self) -> str:
        return self._modelInfo.name  # type: ignore[no-any-return]

    @property
    def modelName(self) -> str:
        return self._modelInfo.modelName  # type: ignore[no-any-return]

    @property
    def modelParams(self) -> "Dict[str, Any]":
        return self._modelInfo.modelParams  # type: ignore[no-any-return]

    @property
    def vendor(self) -> str:
        return self._modelInfo.vendor  # type: ignore[no-any-return]

    @property
    def serialNumber(self) -> str:
        return self._modelInfo.serialNumber  # type: ignore[no-any-return]

    @property
    def supportedEngines(self) -> "List[AcquisitionEngineTypes]":
        return self._modelInfo.supportedEngines  # type: ignore[no-any-return]

    @property
    def category(self) -> str:
        return self._modelInfo.category  # type: ignore[no-any-return]

    @property
    def sensorSize(self) -> "Tuple[int, int]":
        return self._modelInfo.sensorSize  # type: ignore[no-any-return]

    @property
    def pixelSize(self) -> "Tuple[float, float, float]":
        return self._modelInfo.pixelSize  # type: ignore[no-any-return]

    @property
    def exposureEGU(self) -> str:
        return self._modelInfo.exposureEGU  # type: ignore[no-any-return]

    @property
    def pixelPhotometric(self) -> "List[PixelPhotometricTypes]":
        return self._modelInfo.pixelPhotometric  # type: ignore[no-any-return]

    @property
    def bitsPerPixel(self) -> "Set[int]":
        return self._modelInfo.bitsPerPixel  # type: ignore[no-any-return]

    @property
    def binning(self) -> "List[int]":
        return self._modelInfo.binning  # type: ignore[no-any-return]

    @property
    def offset(self) -> "Tuple[int, int]":
        return self._modelInfo.offset  # type: ignore[no-any-return]

    @property
    def shape(self) -> "Tuple[int, int]":
        return self._modelInfo.shape  # type: ignore[no-any-return]
