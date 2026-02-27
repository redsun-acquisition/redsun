import time
from typing import Any

from bluesky.protocols import Descriptor, Reading

from redsun.device import Device, PDevice


class SimpleDevice(Device):
    """A simple test device with configuration."""

    def __init__(self, name: str, value: int = 42) -> None:
        super().__init__(name)
        self.value = value

    def describe_configuration(self) -> dict[str, Descriptor]:
        return {
            "value": {
                "source": self.name,
                "dtype": "integer",
                "shape": [],
            }
        }

    def read_configuration(self) -> dict[str, Reading[Any]]:
        return {
            "value": {
                "value": self.value,
                "timestamp": time.time(),
            }
        }


class ComplexDevice(Device):
    """A more complex test device with multiple configuration fields."""

    def __init__(
        self,
        name: str,
        sensor_size: tuple[int, int] = (10, 10),
        pixel_size: tuple[float, float] = (1.0, 1.0),
    ) -> None:
        super().__init__(name)
        self.sensor_size = sensor_size
        self.pixel_size = pixel_size

    def describe_configuration(self) -> dict[str, Descriptor]:
        return {
            "sensor_size": {
                "source": self.name,
                "dtype": "array",
                "shape": [2],
            },
            "pixel_size": {
                "source": self.name,
                "dtype": "array",
                "shape": [2],
                "units": "μm",
            },
        }

    def read_configuration(self) -> dict[str, Reading[Any]]:
        timestamp = time.time()
        return {
            "sensor_size": {
                "value": self.sensor_size,
                "timestamp": timestamp,
            },
            "pixel_size": {
                "value": self.pixel_size,
                "timestamp": timestamp,
            },
        }


def test_simple_device() -> None:
    """Test basic Device functionality."""
    device = SimpleDevice("test_device")

    assert isinstance(device, PDevice)
    assert device.name == "test_device"
    assert device.parent is None
    assert device.value == 42

    # Test describe_configuration
    descriptor = device.describe_configuration()
    assert "value" in descriptor.keys()
    assert descriptor["value"]["source"] == "test_device"
    assert descriptor["value"]["dtype"] == "integer"
    assert descriptor["value"]["shape"] == []

    # Test read_configuration
    reading = device.read_configuration()
    assert "value" in reading
    assert reading["value"]["value"] == 42
    assert isinstance(reading["value"]["timestamp"], float)


def test_device_with_custom_value() -> None:
    """Test Device with custom initialization."""
    device = SimpleDevice("custom_device", value=100)

    assert device.name == "custom_device"
    assert device.value == 100

    reading = device.read_configuration()
    assert reading["value"]["value"] == 100


def test_complex_device() -> None:
    """Test more complex Device with multiple fields."""
    device = ComplexDevice(
        "complex_device", sensor_size=(20, 30), pixel_size=(2.5, 2.5)
    )

    assert isinstance(device, PDevice)
    assert device.name == "complex_device"
    assert device.sensor_size == (20, 30)
    assert device.pixel_size == (2.5, 2.5)

    # Test describe_configuration
    descriptor = device.describe_configuration()
    assert "sensor_size" in descriptor.keys()
    assert "pixel_size" in descriptor.keys()
    assert descriptor["sensor_size"]["dtype"] == "array"
    assert descriptor["sensor_size"]["shape"] == [2]
    assert descriptor["pixel_size"]["units"] == "μm"

    # Test read_configuration
    reading = device.read_configuration()
    assert reading["sensor_size"]["value"] == (20, 30)
    assert reading["pixel_size"]["value"] == (2.5, 2.5)


def test_device_protocol_compliance() -> None:
    """Test that Device instances comply with PDevice protocol."""
    device = SimpleDevice("protocol_test")

    # Check protocol compliance
    assert isinstance(device, PDevice)
    assert hasattr(device, "name")
    assert hasattr(device, "parent")
    assert hasattr(device, "describe_configuration")
    assert hasattr(device, "read_configuration")
