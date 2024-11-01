from abc import ABC, abstractmethod
from dataclasses import asdict
from typing import TYPE_CHECKING
from redsun.toolkit.utils import create_evented_dataclass
from redsun.toolkit.log import Loggable

if TYPE_CHECKING:
    from typing import List, Dict, Any
    from redsun.toolkit.config import AcquisitionEngineTypes
    from redsun.toolkit.config import MotorModelInfo


class MotorModel(ABC, Loggable):
    """
    `MotorModel` abstract base class. Implements `Loggable` protocol.

    The `MotorModel` is the base class from which all motors, regardless of the supported engine, must inherit.
    It provides the basic information about the motor model and the properties exposable to the upper layers for user interaction.

    It does **not** provide APIs for performing actions, which must be instead defined by the engine-specific motor classes.

    The `MotorModel` contains an extended, evented dataclass that allows the user to expose new properties to the upper layers using `psygnal`.

    Parameters
    ----------
    name : str
        - Motor unique identifier name.
        - User defined.
    model_info: MotorModelInfo
        - Motor model information dataclass.
        - Provided by RedSun configuration.

    Properties
    ----------
    name : str
        - Motor instance unique identifier name.
    modelName: str
        - Motor model name.
    modelParams: dict
        - Motor model parameters dictionary.
    vendor: str
        - Motor vendor.
    serialNumber: str
        - Motor serial number.
    supportedEngines: list[AcquisitionEngineTypes]
        - Supported acquisition engines list.
    category: DetectorModelTypes
        - Motor type.
    stepEGU: str
        - Motor step unit.
    stepSize: float
        - Motor step size.
    axes : list[str]
        - Motor axes.
    returnHome : bool
        - If `True`, motor will return to home position
        (defined as  the initial position the motor had at RedSun's startup)
        after RedSun is closed. Defaults to `False`.
    """

    @abstractmethod
    def __init__(self, name: str, model_info: "MotorModelInfo"):
        FullModelInfo = create_evented_dataclass(
            cls_name=model_info.modelName + "Info",
            original_cls=type(model_info),
            types={"name": str},
            values={"name": name},
        )
        self._modelInfo = FullModelInfo(**asdict(model_info))

    @property
    def name(self) -> str:
        return self._modelInfo.name # type: ignore[no-any-return]

    @property
    def modelName(self) -> str:
        return self._modelInfo.modelName # type: ignore[no-any-return]

    @property
    def modelParams(self) -> "Dict[str, Any]":
        return self._modelInfo.modelParams # type: ignore[no-any-return]

    @property
    def vendor(self) -> str:
        return self._modelInfo.vendor # type: ignore[no-any-return]

    @property
    def serialNumber(self) -> str:
        return self._modelInfo.serialNumber # type: ignore[no-any-return]

    @property
    def supportedEngines(self) -> "List[AcquisitionEngineTypes]":
        return self._modelInfo.supportedEngines # type: ignore[no-any-return]

    @property
    def category(self) -> str:
        return self._modelInfo.category # type: ignore[no-any-return]

    @property
    def stepEGU(self) -> str:
        return self._modelInfo.stepEGU # type: ignore[no-any-return]

    @property
    def stepSize(self) -> float:
        return self._modelInfo.stepSize # type: ignore[no-any-return]

    @property
    def axes(self) -> "List[str]":
        return self._modelInfo.axes # type: ignore[no-any-return]

    @property
    def returnHome(self) -> bool:
        return self._modelInfo.returnHome # type: ignore[no-any-return]
