from sunflare.config import ModelInfo
from bluesky.protocols import Descriptor, Reading
from typing import Any
from attrs import define, field, validators, setters

@define(kw_only=True)
class MockDetectorInfo(ModelInfo):
    """Mock motor model information."""

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

class MockDetector:
    def __init__(self, name: str, model_info: MockDetectorInfo) -> None:
        self._name = name
        self._model_info = model_info

    def read_configuration(self) -> dict[str, Reading[Any]]:
        raise NotImplementedError(
            "Mock detector model does not support read_configuration operation."
        )

    def describe_configuration(self) -> dict[str, Descriptor]:
        raise NotImplementedError(
            "Mock detector model does not support describe_configuration operation."
        )
    
    @property
    def name(self) -> str:
        return self.name
    
    @property
    def model_info(self) -> MockDetectorInfo:
        return self._model_info

    @property
    def parent(self) -> None:
        return None
    
class NonDerivedDetectorInfo:
    def __init__(self, 
                 *, 
                 plugin_name: str, 
                 plugin_id: str, 
                 exposure: float, 
                 egu: str, 
                 sensor_shape: tuple[int, int], 
                 pixel_size: tuple[float, float, float], 
                 integer: int, 
                 floating: float, 
                 string: str) -> None:
        self.plugin_name = plugin_name
        self.plugin_id = plugin_id
        self.exposure = exposure
        self.egu = egu
        self.sensor_shape = sensor_shape
        self.pixel_size = pixel_size
        self.integer = integer
        self.floating = floating
        self.string = string


class NonDerivedDetector:
    def __init__(self, name: str, model_info: NonDerivedDetectorInfo) -> None:
        self._name = name
        self._model_info = model_info
    
    def read_configuration(self) -> dict[str, Reading[Any]]:
        raise NotImplementedError("Mock detector model does not support read_configuration operation.")

    def describe_configuration(self) -> dict[str, Descriptor]:
        raise NotImplementedError("Mock detector model does not support describe_configuration operation.")

    @property
    def name(self) -> str:
        return self._name

    @property
    def model_info(self) -> NonDerivedDetectorInfo:
        return self._model_info
    
    @property
    def parent(self) -> None:
        return None
