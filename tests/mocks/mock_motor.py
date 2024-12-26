from __future__ import annotations

from typing import Any

from sunflare.config import MotorModelInfo
from sunflare.engine import MotorModel, Status

from bluesky.protocols import Location


class MockMotorInfo(MotorModelInfo):
    """Mock motor model information."""

    integer: int
    floating: float
    string: str


class MockMotor(MotorModel[MockMotorInfo]):
    def __init__(self, name: str, model_info: MockMotorInfo) -> None:
        super().__init__(name, model_info)

    def set(self, value: int, *args: Any, **kwargs: Any) -> Status:  # type: ignore[override]
        raise NotImplementedError("Mock motor model does not support set operation.")

    def locate(self) -> Location[int]:  # type: ignore[override]
        raise NotImplementedError("Mock motor model does not support locate operation.")

    def shutdown(self) -> None: ...

    @property
    def integer(self) -> int:
        return self.model_info.integer

    @property
    def floating(self) -> float:
        return self.model_info.floating

    @property
    def string(self) -> str:
        return self.model_info.string
