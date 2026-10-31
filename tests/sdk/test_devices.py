"""Tests for reading the axes, limits and configuration of a device."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest
from ophyd_async.core import (
    AsyncStatus,
    Device,
    DeviceMap,
    DeviceVector,
    MovableLogic,
    StandardMovable,
    StandardReadable,
    StandardReadableFormat,
    soft_signal_rw,
)

from redsun.utils.devices import (
    DevicePath,
    LightInfo,
    Readback,
    describe_axis,
    describe_light,
    device_path,
    held_by,
    is_light,
    limits,
    readback,
)
from tests.sdk.mocks import (
    DimmerLight,
    NumberSwitchDevice,
    SoftAxis,
    SoftLight,
)

if TYPE_CHECKING:
    from bluesky.protocols import Callback, Location


class ThermalAxis(StandardReadable):
    """An axis reading a temperature beside its hinted position, naming no readback."""

    def __init__(self, name: str = "") -> None:
        with self.add_children_as_readables():
            self.temperature = soft_signal_rw(float, 21.0, units="C", precision=1)
        with self.add_children_as_readables(StandardReadableFormat.HINTED_SIGNAL):
            self.position = soft_signal_rw(float, 0.0, units="um", precision=-1)
        super().__init__(name=name)

    @AsyncStatus.wrap
    async def set(self, value: float) -> None:
        """Move to *value*."""
        await self.position.set(value)

    async def locate(self) -> Location[float]:
        """Return the position, which is also the setpoint."""
        position = await self.position.get_value()
        return {"setpoint": position, "readback": position}

    def subscribe_reading(self, function: Callback[float]) -> None:
        """Follow the position."""
        self.position.subscribe(function)

    def clear_sub(self, function: Callback[float]) -> None:
        """Stop following the position."""
        self.position.clear_sub(function)


class TwoHintAxis(StandardReadable, StandardMovable[float]):
    """An axis hinting a temperature before the position it moves."""

    def __init__(self, name: str = "") -> None:
        with self.add_children_as_readables(StandardReadableFormat.HINTED_SIGNAL):
            self.temperature = soft_signal_rw(float, 21.0, units="C")
            self.position = soft_signal_rw(float, 0.0, units="um")
        super().__init__(name=name)

    @property
    def movable_logic(self) -> MovableLogic[float]:
        """Setpoint and readback of the axis, which are its position."""
        return MovableLogic(setpoint=self.position, readback=self.position)


class Float32Axis(SoftAxis):
    """A soft axis reporting its position as a numpy float32."""

    async def locate(self) -> Location[float]:
        """Return the position as numpy float32 values."""
        location = await super().locate()
        return {
            "setpoint": np.float32(location["setpoint"]),  # type: ignore[typeddict-item]
            "readback": np.float32(location["readback"]),  # type: ignore[typeddict-item]
        }


class Leaf(Device):
    """A device holding one signal."""

    def __init__(self, name: str = "") -> None:
        self.power = soft_signal_rw(float)
        super().__init__(name=name)


class Pair(Device):
    """A device holding two leaves."""

    def __init__(self, name: str = "") -> None:
        self.x = Leaf()
        self.y = Leaf()
        super().__init__(name=name)


class Tree(Device):
    """A root holding a device, a `DeviceVector` and a `DeviceMap`."""

    def __init__(self, name: str = "") -> None:
        self.xy = Pair()
        self.channel = DeviceVector({1: Leaf()})
        self.lights = DeviceMap({"laser": Leaf(), "led-blue": Leaf()})
        super().__init__(name=name)


@pytest.fixture
def scope() -> Tree:
    """Return a tree named `scope`."""
    return Tree("scope")


@pytest.mark.parametrize(
    ("descriptor", "expected"),
    [
        pytest.param(
            {"limits": {"control": {"low": -1.0, "high": 2.0}}},
            (-1.0, 2.0),
            id="control",
        ),
        pytest.param(
            {"limits": {"display": {"low": 0.0, "high": 9.0}}}, (0.0, 9.0), id="display"
        ),
        pytest.param(
            {"limits": {"control": {"low": 0.0, "high": 0.0}}},
            (None, None),
            id="epics-none",
        ),
        pytest.param(
            {"limits": {"control": {"high": 5.0}}}, (None, 5.0), id="one-bound"
        ),
        pytest.param({}, (None, None), id="no-limits"),
        pytest.param(
            {
                "limits": {
                    "control": {"low": 1.0, "high": 2.0},
                    "display": {"low": 0.0, "high": 9.0},
                }
            },
            (1.0, 2.0),
            id="control-first",
        ),
        pytest.param(
            {"limits": {"control": {"low": 3.0, "high": 1.0}}},
            (None, None),
            id="reversed",
        ),
    ],
)
def test_limits_are_read_from_a_descriptor(
    descriptor: dict[str, object], expected: tuple[float | None, float | None]
) -> None:
    """Read control limits, else display ones, and count a 0-0 pair as none."""
    assert limits(descriptor) == expected


async def test_an_axis_is_described_by_its_hinted_entry() -> None:
    """Read units from the hinted entry, and drop a negative precision."""
    axis = ThermalAxis("focus")
    await axis.connect(mock=False)

    info = await describe_axis(axis)

    assert (info.readback.units, info.readback.precision) == ("um", None)
    assert info.key == axis.position.name


async def test_a_numpy_position_is_a_number() -> None:
    """Describe an axis whose position is a numpy float32."""
    axis = Float32Axis("focus")
    await axis.connect(mock=False)

    info = await describe_axis(axis)

    assert info.readback.value == pytest.approx(0.0)


async def test_a_movable_axis_is_described_by_its_readback_not_its_first_hint() -> None:
    """Take the key and units of the readback a movable axis names."""
    axis = TwoHintAxis("stage")
    await axis.connect(mock=False)

    info = await describe_axis(axis)

    assert (info.key, info.readback.units) == (axis.position.name, "um")


async def test_a_light_is_described_from_its_signals() -> None:
    """Describe a dimmable light's state and its intensity's units and limits."""
    light = DimmerLight("laser")
    await light.connect(mock=False)
    await light.enabled.set(True)

    info = await describe_light(light)

    assert info == LightInfo(True, Readback(10.0, "mW", 1, (0.0, 100.0)))


async def test_a_light_without_intensity_is_on_or_off_only() -> None:
    """Describe a light that has no intensity with its state alone."""
    light = SoftLight("led")
    await light.connect(mock=False)

    assert await describe_light(light) == LightInfo(False)


async def test_an_enabled_attribute_that_is_not_a_bool_signal_is_no_light() -> None:
    """Refuse a device whose `enabled` is not a boolean signal."""
    shutter = NumberSwitchDevice("shutter")
    await shutter.connect(mock=False)
    led = SoftLight("led")
    await led.connect(mock=False)

    assert (is_light(shutter), is_light(led)) == (False, True)


@pytest.mark.parametrize(
    ("descriptor", "expected"),
    [
        pytest.param(
            {
                "units": "um",
                "precision": 3,
                "limits": {"control": {"low": -1.0, "high": 2.0}},
            },
            Readback(1.5, "um", 3, (-1.0, 2.0)),
            id="all",
        ),
        pytest.param({"units": 5, "precision": -1}, Readback(1.5), id="malformed"),
        pytest.param({"precision": True}, Readback(1.5), id="bool-precision"),
    ],
)
def test_a_readback_keeps_what_its_descriptor_states_well(
    descriptor: dict[str, object], expected: Readback
) -> None:
    """Keep text units, a whole precision of at least 0, and limits, from a descriptor."""
    assert readback(1.5, descriptor) == expected


def test_a_device_path_names_its_root_and_the_way_down(scope: Tree) -> None:
    """Give attributes, container keys and signals their dotted path below the root."""
    assert device_path(scope.xy.x) == DevicePath(
        "scope", ("xy", "x"), ("scope", "scope-xy", "scope-xy-x")
    )
    assert device_path(scope.channel[1]).path == "channel.1"
    assert device_path(scope.lights["led-blue"].power).path == "lights.led-blue.power"
    assert device_path(scope) == DevicePath("scope", (), ("scope",))


def test_a_device_path_reads_as_a_label(scope: Tree) -> None:
    """Render a path as the root, then the path when there is one."""
    assert str(device_path(scope.xy)) == "scope / xy"
    assert str(device_path(scope)) == "scope"
    assert device_path(scope.xy.x).parent == device_path(scope.xy)
    assert device_path(scope).parent is None


def test_a_dotted_key_keeps_its_parent(scope: Tree) -> None:
    """Find the parent of a device whose container key holds a dot."""
    scope.lights["led.1"] = Leaf()
    scope.set_name("scope")

    path = device_path(scope.lights["led.1"])

    assert path.keys == ("lights", "led.1")
    assert path.parent == device_path(scope.lights)


def test_a_device_outside_its_parents_children_starts_its_path(scope: Tree) -> None:
    """Label a device its parent does not list by its own name, keeping the names above."""
    stray = soft_signal_rw(int, name="stray")
    stray.parent = scope.xy

    path = device_path(stray)

    assert str(path) == "stray"
    assert path.names == ("scope", "scope-xy", "stray")
    assert held_by(stray, {"scope"})


@pytest.mark.parametrize(
    ("held", "expected"),
    [
        ({"scope"}, True),
        ({"scope-xy"}, True),
        ({"scope-xy-x"}, True),
        ({"scope-xy-y"}, False),
        ({"scope-xy-x-power"}, False),
        (set(), False),
    ],
)
def test_holding_a_device_holds_what_is_below_it(
    scope: Tree, held: set[str], expected: bool
) -> None:
    """Hold a device when it or a device above it is named, never when only one below it is."""
    assert held_by(scope.xy.x, held) is expected
