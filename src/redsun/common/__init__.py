"""Module for helper types used in the core application."""

from typing import Literal, Type, TypedDict

from sunflare.config import ControllerInfo, DetectorModelInfo, MotorModelInfo
from sunflare.controller import BaseController
from sunflare.engine import DetectorModel, MotorModel


class InfoBackend(TypedDict):
    """Support typed dictionary for backend information models.

    Parameters
    ----------
    detectors : ``dict[str, DetectorModelInfo]``
        Dictionary of detector information models.
    motors : ``dict[str, MotorModelInfo]``
        Dictionary of motor information models.
    controllers : ``dict[str, ControllerInfo]``
        Dictionary of controller information models.
    """

    detectors: dict[str, DetectorModelInfo]
    motors: dict[str, MotorModelInfo]
    controllers: dict[str, ControllerInfo]


class Backend(TypedDict):
    """A support typed dictionary for backend models constructors.

    Parameters
    ----------
    detectors : ``dict[str, Type[DetectorModel[DetectorModelInfo]]]``
        Dictionary of detector device models.
    motors : ``dict[str, Type[MotorModel[MotorModelInfo]]]``
        Dictionary of motor device models.
    controllers : ``dict[str, Type[BaseController]``
        Dictionary of base controllers.
    """

    detectors: dict[str, Type[DetectorModel[DetectorModelInfo]]]
    motors: dict[str, Type[MotorModel[MotorModelInfo]]]
    controllers: dict[str, Type[BaseController]]


#: Plugin group names for the backend.
BACKEND_GROUPS = Literal["detectors", "motors", "controllers"]
