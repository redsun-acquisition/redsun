from typing import Any

from attrs import define, field, setters, validators
from sunflare.config import ModelInfo

@define(kw_only=True)
class MyMotorInfo(ModelInfo):
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

class MyMotor:
    
    def __init__(self, name: str, model_info: MyMotorInfo) -> None:
        self.name = name
        self.model_info = model_info

    def read_configuration(self) -> dict[str, Any]:
        raise NotImplementedError()
    
    def describe_configuration(self) -> dict[str, Any]:
        raise NotImplementedError()
