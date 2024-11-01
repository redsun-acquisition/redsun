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
    """ Detector model for ExEngine.

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
    def arm(self, frame_count: "Optional[int]" = None) -> None:
        """
        Arms the device before an start command. This optional command validates all the current features for
        consistency and prepares the device for a fast start of the Acquisition. If not used explicitly,
        this command will be automatically executed at the first AcquisitionStart but will not be repeated
        for the subsequent ones unless a feature is changed in the device.
        """
        ...

    @abstractmethod
    def start(self) -> None: ...

    @abstractmethod
    def stop(self) -> None: ...

    @abstractmethod
    def is_stopped(self) -> "bool": ...

    @abstractmethod
    def pop_data(
        self, timeout: Optional[float] = None
    ) -> "Tuple[npt.NDArray[Any], Dict[str, Any]]":
        """
        Get the next image and metadata from the camera buffer. If timeout is None, this function will block until
        an image is available. If timeout is a number, this function will block for that many seconds before returning
        (None, None) if no image is available
        """
        ...


class ExEngineMMCameraModel(DetectorModel, ExEngineMMCamera):  # type: ignore[misc]
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
