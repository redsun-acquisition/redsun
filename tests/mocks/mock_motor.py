from __future__ import annotations

from typing import Any, ClassVar

from sunflare.config import MotorModelInfo
from sunflare.engine import MotorModel, Status

from bluesky.protocols import Location

from psygnal import SignalGroupDescriptor


class MockMotorInfo(MotorModelInfo):
    """Mock motor model information."""

    integer: int
    floating: float
    string: str

class NonDerivedMotorInfo:
    """Mock detector model information."""

    integer: int
    floating: float
    string: str
    events: ClassVar[SignalGroupDescriptor] = SignalGroupDescriptor()

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
    

class NonDerivedMotor:

    def __init__(self, name: str, model_info: NonDerivedMotorInfo) -> None:
        self.name = name
        self.model_info = model_info

    def set(self, value: int, *args: Any, **kwargs: Any) -> Status:
        raise NotImplementedError("Mock motor model does not support set operation.")
    
    def locate(self) -> Location[int]:
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


class OtherMotor(MotorModel[MockMotorInfo]):
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
