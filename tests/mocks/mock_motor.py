from __future__ import annotations

from typing import Any

from attrs import define, field, setters, validators

from sunflare.config import ModelInfo
from sunflare.model import ModelProtocol
from sunflare.engine import Status

from bluesky.protocols import Location

@define(kw_only=True)
class MockMotorInfo(ModelInfo):
    """Mock motor model information."""

    axis: list[str] = field(factory=list, on_setattr=setters.frozen)
    step_size: dict[str, float] = field(factory=dict)
    egu: str = field(validator=validators.instance_of(str), on_setattr=setters.frozen)
    integer: int
    floating: float
    string: str

    @axis.validator
    def _validate_axis(self, _: str, value: list[str]) -> None:
        if not all(isinstance(val, str) for val in value):
            raise ValueError("All values in the list must be strings.")
        if len(value) == 0:
            raise ValueError("The list must contain at least one element.")
    @step_size.validator
    def _validate_step_size(self, _: str, value: dict[str, float]) -> None:
        if not all(isinstance(val, float) for val in value.values()):
            raise ValueError("All values in the dictionary must be floats.")
        if len(value) == 0:
            raise ValueError("The dictionary must contain at least one element.")

class NonDerivedMotorInfo:
    """Mock detector model information."""

    axis: list[str]
    step_size: dict[str, float]
    egu: str
    integer: int
    floating: float
    string: str

class MockMotor(ModelProtocol):

    def __init__(self, name: str, model_info: MockMotorInfo) -> None:
        self.name = name
        self.model_info = model_info

    def set(self, value: int, *args: Any, **kwargs: Any) -> Status:  # type: ignore[override]
        raise NotImplementedError("Mock motor model does not support set operation.")

    def locate(self) -> Location[int]:  # type: ignore[override]
        raise NotImplementedError("Mock motor model does not support locate operation.")

    def shutdown(self) -> None: ...

    @property
    def model_info(self) -> MockMotorInfo:
        return self.model_info

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


class OtherMotor(ModelProtocol):
    def __init__(self, name: str, model_info: MockMotorInfo) -> None:
        self.name = name
        self.model_info = model_info

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
