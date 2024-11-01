"""ExEngine detector model available for creating custom device interfaces with the RedSun Toolkit."""

from abc import abstractmethod
from typing import TYPE_CHECKING, Tuple

from exengine.backends.micromanager import MicroManagerCamera as ExEngineMMCamera
from exengine.device_types import Detector as ExEngineDetector

from redsun.toolkit.config import PixelPhotometricTypes
from redsun.toolkit.engine.detector import DetectorModel

if TYPE_CHECKING:
    from typing import Any, Dict, Optional, Union

    import numpy.typing as npt

    from redsun.toolkit.config import DetectorModelInfo


class ExEngineDetectorModel(DetectorModel, ExEngineDetector):  # type: ignore[misc]
    r""" 
    Detector model for ExEngine.

    See `DetectorModel` for more information about initialization. \\
    See the ExEngine documentation for more information about the APIs.
    """

    @abstractmethod
    def __init__(
        self,
        name: "str",
        model_info: "DetectorModelInfo",
        exposure: "Union[int, float]",
        pixel_photometric: "list[PixelPhotometricTypes]" = [PixelPhotometricTypes.GRAY],
        bits_per_pixel: "Optional[set[int]]" = {8},
        binning: "Optional[list[int]]" = [1],
        offset: "Optional[Tuple[int, int]]" = (0, 0),
        shape: "Optional[Tuple[int, int]]" = None,
    ) -> None:
        DetectorModel.__init__(
            self,
            name,
            model_info,
            exposure,
            pixel_photometric,
            bits_per_pixel,
            binning,
            offset,
            shape,
        )

    @abstractmethod
    def arm(self, frame_count: "Optional[int]" = None) -> None:  # noqa: D102
        ...

    @abstractmethod
    def start(self) -> None: ...  # noqa: D102

    @abstractmethod
    def stop(self) -> None: ...  # noqa: D102

    @abstractmethod
    def is_stopped(self) -> "bool": ...  # noqa: D102

    @abstractmethod
    def pop_data(  # noqa: D102
        self, timeout: Optional[float] = None
    ) -> "Tuple[npt.NDArray[Any], Dict[str, Any]]":
        ...


class ExEngineMMCameraModel(DetectorModel, ExEngineMMCamera):  # type: ignore[misc]  # noqa: D101
    def __init__(
        self,
        name: "str",
        model_info: "DetectorModelInfo",
        exposure: "Union[int, float]",
        pixel_photometric: "list[PixelPhotometricTypes]" = [PixelPhotometricTypes.GRAY],
        bits_per_pixel: "Optional[set[int]]" = {8},
        binning: "Optional[list[int]]" = [1],
        offset: "Optional[Tuple[int, int]]" = (0, 0),
        shape: "Optional[Tuple[int, int]]" = None,
    ) -> None:
        DetectorModel.__init__(
            self,
            name,
            model_info,
            exposure,
            pixel_photometric,
            bits_per_pixel,
            binning,
            offset,
            shape,
        )

        # after initializing the general model, initialize the specific camera model
        ExEngineMMCamera.__init__(name=name)
