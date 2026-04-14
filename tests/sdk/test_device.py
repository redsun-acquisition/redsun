"""Tests for redsun device base classes and attribute protocols."""

from __future__ import annotations

from typing import Any

import pytest

from redsun.device import (
    AcquisitionController,
    AttrR,
    AttrRW,
    AttrT,
    AttrW,
    DataWriter,
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
# Helpers — signal-bearing device
# ---------------------------------------------------------------------------


class SignalDevice(Device):
    """Device that exposes configuration through typed soft attributes."""

    def __init__(
        self,
        name: str,
        *,
        value: int = 42,
        label: str = "default",
        position: float = 0.0,
        units: str = "mm",
    ) -> None:
        super().__init__(name)
        self.value = SoftAttrRW[int](value)
        self.label = SoftAttrR[str](label)
        self.position = SoftAttrRW[float](position, units=units)


class MinimalDevice(Device):
    """Device that relies entirely on base-class defaults (no signals)."""

    def __init__(self, name: str) -> None:
        super().__init__(name)


class ChildDevice(Device):
    """Minimal child device for hierarchy tests."""

    def __init__(self, name: str) -> None:
        super().__init__(name)


class ParentDevice(Device):
    """Device that owns a ChildDevice and a SoftAttrRW."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.sub = ChildDevice(name)
        self.speed = SoftAttrRW[float](0.0)


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


class _DataWriterImpl:
    def open(self, name: str, exposures_per_event: int = 1) -> dict[str, Any]:
        return {}

    def get_indices_written(self) -> int:
        return 0

    def observe_indices_written(self, timeout: float) -> Any: ...

    def collect_stream_docs(self, name: str, indices_written: int) -> Any: ...

    def close(self) -> None: ...


class _FlyerControllerImpl:
    def prepare(self, value: Any) -> None: ...

    def kickoff(self) -> None: ...

    def complete(self) -> None: ...

    def stop(self) -> None: ...


# ---------------------------------------------------------------------------
# Device base class — signal-bearing style
# ---------------------------------------------------------------------------


def test_signal_device_identity() -> None:
    device = SignalDevice("cam")
    assert isinstance(device, PDevice)
    assert device.name == "cam"
    assert device.parent is None


def test_signal_device_default_configuration_empty() -> None:
    """describe_configuration and read_configuration stay empty for signal devices."""
    device = SignalDevice("cam")
    assert device.describe_configuration() == {}
    assert device.read_configuration() == {}


def test_signal_device_value_descriptor() -> None:
    device = SignalDevice("cam", value=7)
    desc = device.value.describe()
    assert "cam-value" in desc
    assert desc["cam-value"]["dtype"] == "integer"
    assert desc["cam-value"]["shape"] == []


def test_signal_device_position_descriptor_carries_units() -> None:
    device = SignalDevice("stage", units="um")
    desc = device.position.describe()
    assert "stage-position" in desc
    assert desc["stage-position"]["units"] == "um"


def test_signal_device_value_read_write_round_trip() -> None:
    device = SignalDevice("cam", value=1)
    s = device.value.set(99)
    s.wait(timeout=1.0)
    assert s.success
    assert device.value.get_value() == 99


def test_signal_device_label_is_read_only() -> None:
    """SoftAttrR does not have a set() method."""
    device = SignalDevice("cam", label="test")
    assert not hasattr(device.label, "set")
    assert device.label.get_value() == "test"


def test_signal_device_satisfies_pdevice() -> None:
    device = SignalDevice("cam")
    assert isinstance(device, PDevice)
    assert hasattr(device, "name")
    assert hasattr(device, "parent")
    assert hasattr(device, "describe_configuration")
    assert hasattr(device, "read_configuration")


def test_minimal_device_instantiation() -> None:
    """A Device subclass with no signals is valid."""
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
    assert isinstance(_DataWriterImpl(), DataWriter)


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
    attr = SoftAttrR[int](42, name="device-value")
    assert isinstance(attr, AttrR)


def test_soft_attr_rw_satisfies_attr_rw() -> None:
    attr = SoftAttrRW[float](0.0, name="device-value")
    assert isinstance(attr, AttrRW)
    assert isinstance(attr, AttrR)
    assert isinstance(attr, AttrW)


def test_soft_attr_t_satisfies_attr_t() -> None:
    attr = SoftAttrT(name="device-trigger")
    assert isinstance(attr, AttrT)


def test_soft_attr_r_get_value() -> None:
    attr = SoftAttrR[int](7, name="dev-x")
    assert attr.get_value() == 7


def test_soft_attr_r_read() -> None:
    attr = SoftAttrR[float](3.14, name="dev-x", units="mm")
    reading = attr.read()
    assert "dev-x" in reading
    assert reading["dev-x"]["value"] == 3.14
    assert isinstance(reading["dev-x"]["timestamp"], float)


def test_soft_attr_r_describe_scalar() -> None:
    attr = SoftAttrR[float](1.0, name="dev-x", units="mm")
    desc = attr.describe()
    assert "dev-x" in desc
    assert desc["dev-x"]["dtype"] == "number"
    assert desc["dev-x"]["shape"] == []
    assert desc["dev-x"]["units"] == "mm"
    assert desc["dev-x"]["source"] == "soft://dev-x"


def test_soft_attr_r_describe_bool() -> None:
    attr = SoftAttrR[bool](False, name="dev-enabled")
    assert attr.describe()["dev-enabled"]["dtype"] == "boolean"


def test_soft_attr_r_describe_int() -> None:
    attr = SoftAttrR[int](0, name="dev-count")
    assert attr.describe()["dev-count"]["dtype"] == "integer"


def test_soft_attr_r_describe_array() -> None:
    attr = SoftAttrR[list[float]]([0.0, 1.0, 2.0], name="dev-pos")
    desc = attr.describe()["dev-pos"]
    assert desc["dtype"] == "array"
    assert desc["shape"] == [3]


def test_soft_attr_r_subscribe_called_immediately() -> None:
    attr = SoftAttrR[int](10, name="dev-x")
    received: list[Any] = []
    attr.subscribe(received.append)
    assert len(received) == 1
    assert received[0]["dev-x"]["value"] == 10


def test_soft_attr_r_subscribe_notified_on_change() -> None:
    attr = SoftAttrRW[int](0, name="dev-x")
    received: list[Any] = []
    attr.subscribe(received.append)
    attr.set(99)
    assert received[-1]["dev-x"]["value"] == 99


def test_soft_attr_r_clear_sub() -> None:
    attr = SoftAttrRW[int](0, name="dev-x")
    received: list[Any] = []
    attr.subscribe(received.append)
    attr.clear_sub(received.append)
    attr.set(5)
    assert len(received) == 1  # only the initial call, no further notifications


def test_soft_attr_rw_set_updates_value() -> None:
    attr = SoftAttrRW[float](0.0, name="dev-x")
    s = attr.set(42.0)
    s.wait(timeout=1.0)
    assert s.success
    assert attr.get_value() == 42.0


def test_soft_attr_t_trigger_no_op() -> None:
    attr = SoftAttrT(name="dev-trigger")
    s = attr.trigger()
    s.wait(timeout=1.0)
    assert s.success


def test_soft_attr_t_trigger_calls_action() -> None:
    called: list[bool] = []
    attr = SoftAttrT(action=lambda: called.append(True), name="dev-trigger")
    attr.trigger().wait(timeout=1.0)
    assert called == [True]


def test_soft_attr_r_name() -> None:
    attr = SoftAttrR[float](0.0, name="my-device-speed")
    assert attr.name == "my-device-speed"


# ---------------------------------------------------------------------------
# SoftAttr* — new signature and set_name
# ---------------------------------------------------------------------------


def test_soft_attr_r_positional_value_no_name() -> None:
    attr = SoftAttrR[int](42)
    assert attr.name == ""
    assert attr.get_value() == 42


def test_soft_attr_r_name_keyword() -> None:
    attr = SoftAttrR[int](42, name="dev-x")
    assert attr.name == "dev-x"
    assert "dev-x" in attr.read()
    assert "dev-x" in attr.describe()


def test_soft_attr_r_set_name_updates_read_describe() -> None:
    attr = SoftAttrR[float](3.14, units="mm")
    attr.set_name("stage-pos")
    assert attr.name == "stage-pos"
    assert "stage-pos" in attr.read()
    assert "stage-pos" in attr.describe()
    assert attr.describe()["stage-pos"]["units"] == "mm"


def test_soft_attr_rw_inherits_set_name() -> None:
    attr = SoftAttrRW[int](0)
    attr.set_name("dev-count")
    assert attr.name == "dev-count"


def test_soft_attr_t_positional_action_no_name() -> None:
    called: list[int] = []
    attr = SoftAttrT(action=lambda: called.append(1))
    assert attr.name == ""
    attr.trigger()
    assert called == [1]


def test_soft_attr_t_name_keyword() -> None:
    attr = SoftAttrT(name="dev-trig")
    assert attr.name == "dev-trig"


def test_soft_attr_t_set_name() -> None:
    attr = SoftAttrT()
    attr.set_name("dev-fire")
    assert attr.name == "dev-fire"


# ---------------------------------------------------------------------------
# Child devices
# ---------------------------------------------------------------------------


class AxisDevice(Device):
    """Single-axis device used as a child in composite device tests."""

    def __init__(self, name: str, *, units: str = "mm") -> None:
        super().__init__(name)
        self.position = SoftAttrRW[float](0.0, units=units)


class CompositeDevice(Device):
    """Device that owns two child AxisDevice instances."""

    def __init__(self, name: str, *, units: str = "mm") -> None:
        super().__init__(name)
        self.x = AxisDevice(name, units=units)
        self.y = AxisDevice(name, units=units)
        self.enabled = SoftAttrRW[bool](True)


def test_composite_device_children_are_accessible() -> None:
    dev = CompositeDevice("stage")
    assert hasattr(dev, "x")
    assert hasattr(dev, "y")
    assert dev.x.name == "stage-x"
    assert dev.y.name == "stage-y"


def test_composite_device_children_satisfy_pdevice() -> None:
    dev = CompositeDevice("stage")
    assert isinstance(dev.x, PDevice)
    assert isinstance(dev.y, PDevice)


def test_composite_device_children_parent_is_set() -> None:
    """Children assigned as attributes have parent wired to the composite device."""
    dev = CompositeDevice("stage")
    assert dev.x.parent is dev
    assert dev.y.parent is dev


def test_composite_device_child_signals_have_descriptor_units() -> None:
    dev = CompositeDevice("stage", units="um")
    x_desc = dev.x.position.describe()
    assert "stage-x-position" in x_desc
    assert x_desc["stage-x-position"]["units"] == "um"

    y_desc = dev.y.position.describe()
    assert "stage-y-position" in y_desc
    assert y_desc["stage-y-position"]["units"] == "um"


def test_composite_device_child_signal_set_does_not_affect_sibling() -> None:
    dev = CompositeDevice("stage")
    dev.x.position.set(5.0).wait(timeout=1.0)
    assert dev.x.position.get_value() == pytest.approx(5.0)
    assert dev.y.position.get_value() == pytest.approx(0.0)


def test_composite_own_attr_independent_from_children() -> None:
    dev = CompositeDevice("stage")
    dev.enabled.set(False).wait(timeout=1.0)
    assert dev.enabled.get_value() is False
    # children unaffected
    assert dev.x.position.get_value() == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Device — child device support and name propagation
# ---------------------------------------------------------------------------


def test_child_device_registered_in_children() -> None:
    parent = ParentDevice("parent")
    children = dict(parent.children())
    assert "sub" in children
    assert children["sub"] is parent.sub


def test_child_device_parent_reference() -> None:
    parent = ParentDevice("parent")
    assert parent.sub.parent is parent


def test_root_device_parent_is_none() -> None:
    assert MinimalDevice("root").parent is None


def test_child_device_name_propagated_on_assignment() -> None:
    parent = ParentDevice("stage")
    assert parent.sub.name == "stage-sub"


def test_soft_attr_name_injected_on_assignment() -> None:
    parent = ParentDevice("cam")
    assert parent.speed.name == "cam-speed"


def test_set_name_propagates_to_child_device() -> None:
    parent = ParentDevice("old")
    parent.set_name("new")
    assert parent.name == "new"
    assert parent.sub.name == "new-sub"


def test_set_name_propagates_to_soft_attr() -> None:
    parent = ParentDevice("cam")
    parent.set_name("sensor")
    assert parent.speed.name == "sensor-speed"


def test_soft_attr_auto_named_via_direct_setattr() -> None:
    """SoftAttr name injected even via direct assignment after __init__."""

    class DynDevice(Device):
        def __init__(self, name: str) -> None:
            super().__init__(name)

    d = DynDevice("dev")
    d.velocity = SoftAttrRW[float](1.0)  # type: ignore[attr-defined]
    assert d.velocity.name == "dev-velocity"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# ophyd-async devices
# ---------------------------------------------------------------------------


def test_oa_standard_readable_satisfies_pdevice() -> None:
    """ophyd_async.core.StandardReadable satisfies PDevice structurally."""
    from ophyd_async.core import StandardReadable, soft_signal_rw

    class OAMotor(StandardReadable):
        def __init__(self, name: str, /, *, units: str = "mm") -> None:
            self.x = soft_signal_rw(float, units=units)
            self.y = soft_signal_rw(float, units=units)
            super().__init__(name=name)

    m = OAMotor("oa_motor")
    assert isinstance(m, PDevice)
    assert m.name == "oa_motor"
    assert m.parent is None


def test_oa_device_has_no_egu_attribute() -> None:
    """Units must come from descriptors only — no top-level egu attribute."""
    from ophyd_async.core import StandardReadable, soft_signal_rw

    class OADetector(StandardReadable):
        def __init__(self, name: str, /, *, exposure_units: str = "ms") -> None:
            self.exposure = soft_signal_rw(float, units=exposure_units)
            super().__init__(name=name)

    det = OADetector("cam")
    assert not hasattr(det, "egu")
    assert not hasattr(det, "exposure_units")


async def test_oa_device_descriptor_carries_units() -> None:
    """After mock-connect, signal descriptors contain the configured units."""
    from ophyd_async.core import StandardReadable, soft_signal_rw

    class OAMotor(StandardReadable):
        def __init__(self, name: str, /, *, units: str = "mm") -> None:
            self.x = soft_signal_rw(float, units=units)
            super().__init__(name=name)

    m = OAMotor("stage", units="um")
    await m.connect(mock=True)
    desc = await m.x.describe()
    assert "stage-x" in desc
    assert desc["stage-x"]["units"] == "um"


async def test_oa_device_read_write_round_trip() -> None:
    """Mock-connected soft signal supports set/get round-trip."""
    from ophyd_async.core import StandardReadable, soft_signal_rw

    class OAMotor(StandardReadable):
        def __init__(self, name: str, /) -> None:
            self.x = soft_signal_rw(float, units="mm")
            super().__init__(name=name)

    m = OAMotor("stage")
    await m.connect(mock=True)
    await m.x.set(42.0)
    reading = await m.x.read()
    assert reading["stage-x"]["value"] == pytest.approx(42.0)


async def test_oa_child_device_descriptor_scoped_by_name() -> None:
    """Child ophyd-async devices scope their signal names under the parent name."""
    from ophyd_async.core import Device as OADevice
    from ophyd_async.core import StandardReadable, soft_signal_rw

    class OAAxis(OADevice):
        def __init__(self, name: str = "") -> None:
            self.position = soft_signal_rw(float, units="mm")
            super().__init__(name=name)

    class OAStage(StandardReadable):
        def __init__(self, name: str, /) -> None:
            self.x = OAAxis()
            self.y = OAAxis()
            super().__init__(name=name)

    stage = OAStage("stage")
    await stage.connect(mock=True)
    desc = await stage.x.position.describe()
    # ophyd-async prefixes child signal names with the parent device name
    assert "stage-x-position" in desc
    assert desc["stage-x-position"]["units"] == "mm"
