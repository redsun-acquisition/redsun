from typing import Any

from attrs import define, field, setters, validators
from bluesky.protocols import Descriptor, Reading
from sunflare.device import Device


@define(kw_only=True)
class MockDetector(Device):
    """Mock detector device."""

    exposure: float = field(validator=validators.instance_of(float))
    egu: str = field(
        default="s", validator=validators.instance_of(str), on_setattr=setters.frozen
    )
    sensor_shape: tuple[int, int] = field(converter=tuple, on_setattr=setters.frozen)
    pixel_size: tuple[float, float, float] = field(converter=tuple)
    integer: int
    floating: float
    string: str

    @sensor_shape.validator
    def _validate_sensor_shape(
        self, _: Any, value: tuple[int, ...]
    ) -> None:
        if not all(isinstance(val, int) for val in value):
            raise ValueError("All values in the tuple must be integers.")
        if len(value) != 2:
            raise ValueError("The tuple must contain exactly two values.")

    @pixel_size.validator
    def _validate_pixel_size(
        self, _: Any, value: tuple[float, ...]
    ) -> None:
        if not all(isinstance(val, float) for val in value):
            raise ValueError("All values in the tuple must be floats.")
        if len(value) != 3:
            raise ValueError("The tuple must contain exactly three values.")

    def __init__(self, name: str, /, **kwargs: Any) -> None:
        super().__init__(name)
        self.__attrs_init__(**kwargs)

    def read_configuration(self) -> dict[str, Reading[Any]]:
        raise NotImplementedError()

    def describe_configuration(self) -> dict[str, Descriptor]:
        raise NotImplementedError()

    @property
    def parent(self) -> None:
        return None


@define(kw_only=True, slots=False)
class NonDerivedDetector:
    """Mock non-derived detector for structural protocol testing."""

    exposure: float
    egu: str
    sensor_shape: tuple[int, int]
    pixel_size: tuple[float, float, float]
    integer: int
    floating: float
    string: str

    def __init__(self, name: str, /, **kwargs: Any) -> None:
        self._name = name
        self.__attrs_init__(**kwargs)

    def read_configuration(self) -> dict[str, Reading[Any]]:
        raise NotImplementedError()

    def describe_configuration(self) -> dict[str, Descriptor]:
        raise NotImplementedError()

    @property
    def parent(self) -> None:
        return None
    
    @property
    def name(self) -> str:
        return self._name
