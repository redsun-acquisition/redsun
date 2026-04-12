"""Tests for redsun device base classes and attribute protocols."""

from __future__ import annotations

import time
from typing import Any

import pytest
from bluesky.protocols import Descriptor, Reading

from redsun.device import (
    AcquisitionController,
    AcquisitionWriter,
    AttrR,
    AttrRW,
    AttrT,
    AttrW,
    Device,
    FlyerController,
    PDevice,
    SoftAttrR,
    SoftAttrRW,
    SoftAttrT,
    TriggerInfo,
    TriggerType,
)

# ---------------------------------------------------------------------------
# Helpers — manual-override style (legacy approach, still supported)
# ---------------------------------------------------------------------------


class SimpleDevice(Device):
    """Device that manually implements configuration methods."""

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
    """Device with multiple manually-declared configuration fields."""

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


class MinimalDevice(Device):
    """Device that relies on the base-class defaults for configuration."""

    def __init__(self, name: str) -> None:
        super().__init__(name)


# ---------------------------------------------------------------------------
# Helpers — minimal structural implementations for protocol checks
# ---------------------------------------------------------------------------


class _AttrRImpl:
    name = "test-attr"

    def read(self) -> dict[str, Any]:
        return {}

    def describe(self) -> dict[str, Any]:
        return {}

    def subscribe(self, function: Any) -> None: ...

    def clear_sub(self, function: Any) -> None: ...

    def get_value(self) -> int:
        return 0


class _AttrWImpl:
    name = "test-attr"

    def set(self, value: Any) -> Any: ...


class _AttrRWImpl(_AttrRImpl, _AttrWImpl): ...


class _AttrTImpl:
    name = "test-attr"

    def trigger(self) -> Any: ...


class _TriggerInfoImpl:
    number_of_events = 10
    trigger = TriggerType.INTERNAL
    deadtime = 0.001
    livetime = 0.1
    exposures_per_event = 1


class _AcquisitionControllerImpl:
    def get_deadtime(self, exposure: float | None) -> float:
        return 0.001

    def prepare(self, trigger_info: Any) -> None: ...

    def arm(self) -> None: ...

    def wait_for_idle(self) -> None: ...

    def disarm(self) -> None: ...


class _AcquisitionWriterImpl:
    def open(self, name: str, exposures_per_event: int = 1) -> dict[str, Any]:
        return {}

    def observe_indices_written(self, timeout: float) -> Any: ...

    def collect_stream_docs(self, name: str, indices_written: int) -> Any: ...

    def close(self) -> None: ...


class _FlyerControllerImpl:
    def prepare(self, value: Any) -> None: ...

    def kickoff(self) -> None: ...

    def complete(self) -> None: ...

    def stop(self) -> None: ...


# ---------------------------------------------------------------------------
# Device base class — manual override style
# ---------------------------------------------------------------------------


def test_simple_device() -> None:
    device = SimpleDevice("test_device")

    assert isinstance(device, PDevice)
    assert device.name == "test_device"
    assert device.parent is None
    assert device.value == 42

    descriptor = device.describe_configuration()
    assert "value" in descriptor
    assert descriptor["value"]["source"] == "test_device"
    assert descriptor["value"]["dtype"] == "integer"
    assert descriptor["value"]["shape"] == []

    reading = device.read_configuration()
    assert "value" in reading
    assert reading["value"]["value"] == 42
    assert isinstance(reading["value"]["timestamp"], float)


def test_device_with_custom_value() -> None:
    device = SimpleDevice("custom_device", value=100)

    assert device.name == "custom_device"
    assert device.value == 100
    assert device.read_configuration()["value"]["value"] == 100


def test_complex_device() -> None:
    device = ComplexDevice(
        "complex_device", sensor_size=(20, 30), pixel_size=(2.5, 2.5)
    )

    assert isinstance(device, PDevice)
    descriptor = device.describe_configuration()
    assert descriptor["sensor_size"]["dtype"] == "array"
    assert descriptor["sensor_size"]["shape"] == [2]
    assert descriptor["pixel_size"]["units"] == "μm"

    reading = device.read_configuration()
    assert reading["sensor_size"]["value"] == (20, 30)
    assert reading["pixel_size"]["value"] == (2.5, 2.5)


def test_device_protocol_compliance() -> None:
    device = SimpleDevice("protocol_test")

    assert isinstance(device, PDevice)
    assert hasattr(device, "name")
    assert hasattr(device, "parent")
    assert hasattr(device, "describe_configuration")
    assert hasattr(device, "read_configuration")


# ---------------------------------------------------------------------------
# Device base class — default (signal-bearing) style
# ---------------------------------------------------------------------------


def test_minimal_device_instantiation() -> None:
    """A Device subclass with no configuration overrides is now valid."""
    device = MinimalDevice("minimal")

    assert isinstance(device, PDevice)
    assert device.name == "minimal"
    assert device.parent is None


def test_minimal_device_default_configuration() -> None:
    """Default describe_configuration and read_configuration return empty dicts."""
    device = MinimalDevice("minimal")

    assert device.describe_configuration() == {}
    assert device.read_configuration() == {}


def test_device_requires_name_argument() -> None:
    """Device.__init__ must remain abstract; direct instantiation is forbidden."""
    with pytest.raises(TypeError):
        Device()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Attribute protocols
# ---------------------------------------------------------------------------


def test_attr_r_structural_compliance() -> None:
    assert isinstance(_AttrRImpl(), AttrR)


def test_attr_r_requires_get_value() -> None:
    """A bare Readable+Subscribable without get_value does not satisfy AttrR."""

    class _Bare:
        name = "x"

        def read(self) -> dict[str, Any]:
            return {}

        def describe(self) -> dict[str, Any]:
            return {}

        def subscribe(self, f: Any) -> None: ...

        def clear_sub(self, f: Any) -> None: ...

    assert not isinstance(_Bare(), AttrR)


def test_attr_w_structural_compliance() -> None:
    assert isinstance(_AttrWImpl(), AttrW)


def test_attr_rw_structural_compliance() -> None:
    obj = _AttrRWImpl()
    assert isinstance(obj, AttrRW)
    assert isinstance(obj, AttrR)
    assert isinstance(obj, AttrW)


def test_attr_t_structural_compliance() -> None:
    assert isinstance(_AttrTImpl(), AttrT)


# ---------------------------------------------------------------------------
# TriggerType
# ---------------------------------------------------------------------------


def test_trigger_type_is_str() -> None:
    """TriggerType values compare equal to their string representations."""
    assert TriggerType.INTERNAL == "internal"
    assert TriggerType.EDGE_TRIGGER == "edge_trigger"
    assert TriggerType.CONSTANT_GATE == "constant_gate"
    assert TriggerType.VARIABLE_GATE == "variable_gate"


def test_trigger_type_is_str_instance() -> None:
    assert isinstance(TriggerType.INTERNAL, str)


# ---------------------------------------------------------------------------
# Acquisition protocols
# ---------------------------------------------------------------------------


def test_trigger_info_structural_compliance() -> None:
    assert isinstance(_TriggerInfoImpl(), TriggerInfo)


def test_trigger_info_missing_field() -> None:
    class _Incomplete:
        number_of_events = 1
        trigger = TriggerType.INTERNAL
        # missing deadtime, livetime, exposures_per_event

    assert not isinstance(_Incomplete(), TriggerInfo)


def test_acquisition_controller_structural_compliance() -> None:
    assert isinstance(_AcquisitionControllerImpl(), AcquisitionController)


def test_acquisition_controller_missing_method() -> None:
    class _Incomplete:
        def get_deadtime(self, exposure: float | None) -> float:
            return 0.0

        def prepare(self, trigger_info: Any) -> None: ...

        # missing arm, wait_for_idle, disarm

    assert not isinstance(_Incomplete(), AcquisitionController)


def test_acquisition_writer_structural_compliance() -> None:
    assert isinstance(_AcquisitionWriterImpl(), AcquisitionWriter)


def test_flyer_controller_structural_compliance() -> None:
    assert isinstance(_FlyerControllerImpl(), FlyerController)


def test_flyer_controller_missing_method() -> None:
    class _Incomplete:
        def prepare(self, value: Any) -> None: ...

        def kickoff(self) -> None: ...

        # missing complete, stop

    assert not isinstance(_Incomplete(), FlyerController)


# ---------------------------------------------------------------------------
# SoftAttr concrete implementations
# ---------------------------------------------------------------------------


def test_soft_attr_r_satisfies_attr_r() -> None:
    attr = SoftAttrR("device-value", 42)
    assert isinstance(attr, AttrR)


def test_soft_attr_rw_satisfies_attr_rw() -> None:
    attr = SoftAttrRW("device-value", 0.0)
    assert isinstance(attr, AttrRW)
    assert isinstance(attr, AttrR)
    assert isinstance(attr, AttrW)


def test_soft_attr_t_satisfies_attr_t() -> None:
    attr = SoftAttrT("device-trigger")
    assert isinstance(attr, AttrT)


def test_soft_attr_r_get_value() -> None:
    attr = SoftAttrR("dev-x", 7)
    assert attr.get_value() == 7


def test_soft_attr_r_read() -> None:
    attr = SoftAttrR("dev-x", 3.14, units="mm")
    reading = attr.read()
    assert "dev-x" in reading
    assert reading["dev-x"]["value"] == 3.14
    assert isinstance(reading["dev-x"]["timestamp"], float)


def test_soft_attr_r_describe_scalar() -> None:
    attr = SoftAttrR("dev-x", 1.0, units="mm")
    desc = attr.describe()
    assert "dev-x" in desc
    assert desc["dev-x"]["dtype"] == "number"
    assert desc["dev-x"]["shape"] == []
    assert desc["dev-x"]["units"] == "mm"
    assert desc["dev-x"]["source"] == "soft://dev-x"


def test_soft_attr_r_describe_bool() -> None:
    attr = SoftAttrR("dev-enabled", False)
    assert attr.describe()["dev-enabled"]["dtype"] == "boolean"


def test_soft_attr_r_describe_int() -> None:
    attr = SoftAttrR("dev-count", 0)
    assert attr.describe()["dev-count"]["dtype"] == "integer"


def test_soft_attr_r_describe_array() -> None:
    attr = SoftAttrR("dev-pos", [0.0, 1.0, 2.0])
    desc = attr.describe()["dev-pos"]
    assert desc["dtype"] == "array"
    assert desc["shape"] == [3]


def test_soft_attr_r_subscribe_called_immediately() -> None:
    attr = SoftAttrR("dev-x", 10)
    received: list[Any] = []
    attr.subscribe(received.append)
    assert len(received) == 1
    assert received[0]["dev-x"]["value"] == 10


def test_soft_attr_r_subscribe_notified_on_change() -> None:
    attr = SoftAttrRW("dev-x", 0)
    received: list[Any] = []
    attr.subscribe(received.append)
    attr.set(99)
    assert received[-1]["dev-x"]["value"] == 99


def test_soft_attr_r_clear_sub() -> None:
    attr = SoftAttrRW("dev-x", 0)
    received: list[Any] = []
    attr.subscribe(received.append)
    attr.clear_sub(received.append)
    attr.set(5)
    assert len(received) == 1  # only the initial call, no further notifications


def test_soft_attr_rw_set_updates_value() -> None:
    attr = SoftAttrRW("dev-x", 0.0)
    s = attr.set(42.0)
    s.wait(timeout=1.0)
    assert s.success
    assert attr.get_value() == 42.0


def test_soft_attr_t_trigger_no_op() -> None:
    attr = SoftAttrT("dev-trigger")
    s = attr.trigger()
    s.wait(timeout=1.0)
    assert s.success


def test_soft_attr_t_trigger_calls_action() -> None:
    called: list[bool] = []
    attr = SoftAttrT("dev-trigger", action=lambda: called.append(True))
    attr.trigger().wait(timeout=1.0)
    assert called == [True]


def test_soft_attr_r_name() -> None:
    attr = SoftAttrR("my-device-speed", 0.0)
    assert attr.name == "my-device-speed"
