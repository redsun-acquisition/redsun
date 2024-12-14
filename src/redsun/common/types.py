# noqa: D100

from typing import TYPE_CHECKING, TypedDict

if TYPE_CHECKING:
    from typing import Union, Type, TypeAlias, Tuple, Any, Optional
    from sunflare.controller.bluesky import BlueskyController
    from sunflare.controller.exengine import ExEngineController
    from sunflare.engine import DetectorModel, MotorModel
    from sunflare.config import (
        DetectorModelInfo,
        MotorModelInfo,
        ControllerInfo,
        AcquisitionEngineTypes,
        FrontendTypes,
    )

InfoTypes: TypeAlias = Union[
    Type[DetectorModelInfo], Type[MotorModelInfo], Type[ControllerInfo]
]
BuildTypes: TypeAlias = Union[
    Type[DetectorModel],
    Type[MotorModel],
    Type[BlueskyController],
    Type[ExEngineController],
]

Registry: TypeAlias = dict[str, list[Tuple[str, InfoTypes, BuildTypes]]]


# TODO: RedSunInstanceInfo should be replaced by this. The original intent was to be able to
#       dump to file via pydantic the configuration information. This may be a better
#       approach and more coherent with the plugin-driven architecture.
# TODO: which types should be used for the dictionary fields?
class RedSunConfigInfo(TypedDict):
    """Typed dictionary for RedSun configuration.

    The dictionary holds the information parsed from the input configuration file.
    They are used from the internal factory classes to build the model and controller
    information objects. The latter are later built into the main hardware controller.

    Parameters
    ----------
    engine : AcquisitionEngineTypes
        Selected acquisition engine.
    frontend : FrontendTypes
        Selected frontend.
    motors : dict[str, MotorModelInfo]
        Dictionary containing motor models information.
    detectors : dict[str, DetectorModelInfo]
        Dictionary containing detector models information.
    controllers : dict[str, ControllerInfo]
        Dictionary containing controller information.
    """

    engine: AcquisitionEngineTypes
    frontend: FrontendTypes
    motors: Optional[dict[str, dict[str, Any]]]
    detectors: Optional[dict[str, dict[str, Any]]]
    controllers: Optional[dict[str, dict[str, Any]]]
