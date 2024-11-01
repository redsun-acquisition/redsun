"""Light source model abstract base class definition."""

from abc import ABC, abstractmethod
from dataclasses import asdict
from typing import TYPE_CHECKING

from redsun.toolkit.log import Loggable
from redsun.toolkit.utils import create_evented_dataclass

if TYPE_CHECKING:
    from typing import Any, Dict, List, Union

    from redsun.toolkit.config import (
        AcquisitionEngineTypes,
        LightModelInfo,
        LightModelTypes,
    )


class LightModel(ABC, Loggable):
    """
    `LightModel` abstract base class. Implements `Loggable` protocol.

    The `LightModel` is the base class from which all light sources, regardless of the supported engine, must inherit.
    It provides the basic information about the light source model and the properties exposable to the upper layers for user interaction.

    It does **not** provide APIs for performing actions, which must be instead defined by the engine-specific light source classes.

    The `LightModel` contains an extended, evented dataclass that allows the user to expose new properties to the upper layers using `psygnal`.

    Parameters
    ----------
    name: str
        - Light source instance unique identifier name.
        - User defined.
    model_info: LightModelInfo
        - Light source model information dataclass.
        - Provided by RedSun configuration.
    """

    @abstractmethod
    def __init__(self, name: str, model_info: "LightModelInfo") -> None:
        FullModelInfo = create_evented_dataclass(
            cls_name=model_info.modelName + "Info",
            original_cls=type(model_info),
            types={"name": str},
            values={"name": name},
        )
        self._modelInfo = FullModelInfo(**asdict(model_info))

    @property
    def name(self) -> str:
        """Light source instance unique identifier name."""
        return self._modelInfo.name  # type: ignore[no-any-return]

    @property
    def modelName(self) -> str:
        """Light source model name."""
        return self._modelInfo.modelName  # type: ignore[no-any-return]

    @property
    def modelParams(self) -> "Dict[str, Any]":
        """Light source model parameters."""
        return self._modelInfo.modelParams  # type: ignore[no-any-return]

    @property
    def vendor(self) -> str:
        """Light source vendor."""
        return self._modelInfo.vendor  # type: ignore[no-any-return]

    @property
    def serialNumber(self) -> str:
        """Light source serial number."""
        return self._modelInfo.serialNumber  # type: ignore[no-any-return]

    @property
    def supportedEngines(self) -> "List[AcquisitionEngineTypes]":
        """List of supported acquisition engines."""
        return self._modelInfo.supportedEngines  # type: ignore[no-any-return]

    @property
    def category(self) -> "LightModelTypes":
        """Light source type."""
        return self._modelInfo.category  # type: ignore[no-any-return]

    @property
    def wavelength(self) -> int:
        """Light source wavelength."""
        return self._modelInfo.wavelength  # type: ignore[no-any-return]

    @property
    def powerEGU(self) -> str:
        """Light source power EGU."""
        return self._modelInfo.powerEGU  # type: ignore[no-any-return]

    @property
    def minPower(self) -> "Union[float, int]":
        """Minimum light source power, expressed in EGU."""
        return self._modelInfo.minPower  # type: ignore[no-any-return]

    @property
    def maxPower(self) -> "Union[float, int]":
        """Maximum light source power, expressed in EGU."""
        return self._modelInfo.maxPower  # type: ignore[no-any-return]

    @property
    def powerStep(self) -> "Union[float, int]":
        """Light source power step, expressed in EGU."""
        return self._modelInfo.powerStep  # type: ignore[no-any-return]
