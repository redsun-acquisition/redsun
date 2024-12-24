"""Custom types for RedSun."""

from __future__ import annotations

from typing import Tuple, Type, TypeAlias, Union

from sunflare.config import (
    ControllerInfo,
    DetectorModelInfo,
    MotorModelInfo,
)
from sunflare.controller import BaseController
from sunflare.engine import DetectorModel, MotorModel

InfoTypes = Union[Type[DetectorModelInfo], Type[MotorModelInfo], Type[ControllerInfo]]
BuildTypes = Union[
    Type[DetectorModel[DetectorModelInfo]],
    Type[MotorModel[MotorModelInfo]],
    Type[BaseController],
]

Registry = dict[str, list[Tuple[str, InfoTypes, BuildTypes]]]
