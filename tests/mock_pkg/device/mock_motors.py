from typing import Any

from attrs import define, field, setters, validators
from sunflare.device import Device


@define(kw_only=True)
class MyMotor(Device):
    """Mock motor device."""

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

    def __init__(self, name: str, /, **kwargs: Any) -> None:
        super().__init__(name)
        self.__attrs_init__(**kwargs)

    def read_configuration(self) -> dict[str, Any]:
        raise NotImplementedError()

    def describe_configuration(self) -> dict[str, Any]:
        raise NotImplementedError()

    @property
    def parent(self) -> None:
        return None


@define(kw_only=True, slots=False)
class NonDerivedMotor:
    """Mock non-derived motor for structural protocol testing."""

    axis: list[str]
    step_size: dict[str, float]
    egu: str
    integer: int
    floating: float
    string: str

    def __init__(self, name: str, /, **kwargs: Any) -> None:
        self._name = name
        self.__attrs_init__(**kwargs)

    def read_configuration(self) -> dict[str, Any]:
        raise NotImplementedError()

    def describe_configuration(self) -> dict[str, Any]:
        raise NotImplementedError()

    @property
    def parent(self) -> None:
        return None

    @property
    def name(self) -> str:
        return self._name
