from typing import ClassVar, Optional

from attrs import Attribute, define, field
from psygnal import SignalGroupDescriptor
from sunflare.config import ControllerInfo


@define
class MotorControllerInfo(ControllerInfo):
    """Motor controller information model.

    This container holds information on all the models that must
    be registered with the motor controller. The models are registered
    in the controller with the ``models`` attribute.

    If no ``models`` field exists or the field is an empty list,
    the controller will register all models available in the
    configuration compatible with the ``MotorProtocol``.

    Attributes
    ----------
    models: ``list[str]``, optional
        List of motor models to be used. The values of the list correspont to the
        names of the models that are to be registered to the controller.
    """

    models: Optional[list[str]] = field(
        default=None,
    )

    # begin: non-public attributes
    axes: Optional[dict[str, list[str]]] = field(
        init=False,
        default=None,
    )
    step_sizes: Optional[dict[str, dict[str, float]]] = field(
        init=False,
        default=None,
    )
    egu: Optional[dict[str, str]] = field(
        init=False,
        default=None,
    )
    # end: non-public attributes
    events: ClassVar[SignalGroupDescriptor] = SignalGroupDescriptor()

    @models.validator
    def _validate_models(
        self, _: Attribute[list[str]], value: Optional[list[str]]
    ) -> None:
        if value is not None and not all(isinstance(model, str) for model in value):
            raise ValueError("All models must be strings.")


@define
class DetectorControllerInfo(ControllerInfo):
    """Detector controller information model.

    Attributes
    ----------
    detectors: ``list[str]``, optional
        List of detectors to be used. The values of the list correspont to the
        names of the detectors that are to be registered to the controller.
    """

    detectors: Optional[list[str]] = field(
        default=None,
    )

    @detectors.validator
    def _validate_detectors(
        self, _: Attribute[list[str]], value: Optional[list[str]]
    ) -> None:
        if value is not None and not all(
            isinstance(detector, str) for detector in value
        ):
            raise ValueError("All detectors must be strings.")
