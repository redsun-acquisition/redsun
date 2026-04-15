"""Smoke tests for the redsun device layer (ophyd-async re-exports)."""

from __future__ import annotations

import numpy as np
import pytest
from ophyd_async.core import (
    Device,
    SignalRW,
    StandardReadable,
    soft_signal_r_and_setter,
    soft_signal_rw,
)

import redsun.device as dev
from redsun.device import AsyncStatus, DetectorWriter, HasCache

# ---------------------------------------------------------------------------
# Re-export smoke tests — verify the public API surface
# ---------------------------------------------------------------------------


def test_device_re_exports_are_importable() -> None:
    """Every symbol listed in redsun.device.__all__ is importable."""
    for name in dev.__all__:
        assert hasattr(dev, name), f"redsun.device missing re-export: {name}"


def test_hascache_is_exported() -> None:
    assert HasCache is not None


def test_async_status_is_exported() -> None:
    assert AsyncStatus is not None


def test_detector_writer_is_abstract() -> None:
    """DetectorWriter is an ABC — direct instantiation must raise."""
    with pytest.raises(TypeError):
        DetectorWriter()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# StandardReadable + soft_signal_rw — basic connect/read/write
# ---------------------------------------------------------------------------


class _SimpleMotor(StandardReadable):
    x: SignalRW[float]
    y: SignalRW[float]

    def __init__(self, name: str, /, *, units: str = "mm") -> None:
        with self.add_children_as_readables():
            self.x = soft_signal_rw(float, initial_value=0.0, units=units)
            self.y = soft_signal_rw(float, initial_value=0.0, units=units)
        super().__init__(name=name)


async def test_device_connect_mock() -> None:
    motor = _SimpleMotor("stage")
    await motor.connect(mock=True)
    assert motor.name == "stage"
    assert await motor.x.get_value() == pytest.approx(0.0)


async def test_soft_signal_rw_set_get() -> None:
    motor = _SimpleMotor("stage", units="um")
    await motor.connect(mock=True)
    await motor.x.set(3.14)
    assert await motor.x.get_value() == pytest.approx(3.14)


async def test_soft_signal_rw_read_contains_name() -> None:
    motor = _SimpleMotor("cam", units="ms")
    await motor.connect(mock=True)
    reading = await motor.x.read()
    assert "cam-x" in reading
    assert reading["cam-x"]["value"] == pytest.approx(0.0)


async def test_device_descriptor_carries_units() -> None:
    motor = _SimpleMotor("stage", units="um")
    await motor.connect(mock=True)
    desc = await motor.x.describe()
    assert "stage-x" in desc
    assert desc["stage-x"]["units"] == "um"


async def test_device_read_write_round_trip() -> None:
    motor = _SimpleMotor("stage")
    await motor.connect(mock=True)
    await motor.x.set(42.0)
    reading = await motor.x.read()
    assert reading["stage-x"]["value"] == pytest.approx(42.0)


# ---------------------------------------------------------------------------
# soft_signal_r_and_setter
# ---------------------------------------------------------------------------


async def test_soft_signal_r_and_setter_basic() -> None:
    sig, setter = soft_signal_r_and_setter(int, initial_value=0, name="counter")
    await sig.connect(mock=False)
    received: list[int] = []
    sig.subscribe(
        lambda reading: received.append(next(iter(reading.values()))["value"])
    )
    setter(42)
    assert 42 in received


async def test_soft_signal_r_and_setter_multiple_updates() -> None:
    sig, setter = soft_signal_r_and_setter(float, initial_value=0.0, name="val")
    await sig.connect(mock=False)
    setter(1.0)
    setter(2.0)
    assert await sig.get_value() == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# Child device hierarchy — name scoping
# ---------------------------------------------------------------------------


class _Axis(Device):
    position: SignalRW[float]

    def __init__(self, name: str = "") -> None:
        self.position = soft_signal_rw(float, initial_value=0.0, units="mm")
        super().__init__(name=name)


class _Stage(StandardReadable):
    x: _Axis
    y: _Axis

    def __init__(self, name: str, /) -> None:
        self.x = _Axis()
        self.y = _Axis()
        super().__init__(name=name)


async def test_child_device_name_scoped_by_parent() -> None:
    stage = _Stage("stage")
    await stage.connect(mock=True)
    desc = await stage.x.position.describe()
    assert "stage-x-position" in desc
    assert desc["stage-x-position"]["units"] == "mm"


async def test_child_device_sibling_independence() -> None:
    stage = _Stage("stage")
    await stage.connect(mock=True)
    await stage.x.position.set(5.0)
    assert await stage.x.position.get_value() == pytest.approx(5.0)
    assert await stage.y.position.get_value() == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Device — no EGU top-level attribute
# ---------------------------------------------------------------------------


def test_oa_device_has_no_egu_attribute() -> None:
    """Units must come from descriptors only — no top-level egu attribute."""

    class OADetector(StandardReadable):
        def __init__(self, name: str, /, *, exposure_units: str = "ms") -> None:
            self.exposure = soft_signal_rw(float, units=exposure_units)
            super().__init__(name=name)

    det = OADetector("cam")
    assert not hasattr(det, "egu")
    assert not hasattr(det, "exposure_units")


# ---------------------------------------------------------------------------
# StandardReadable — satisfies Device
# ---------------------------------------------------------------------------


def test_standard_readable_is_device_subclass() -> None:
    assert issubclass(StandardReadable, Device)


def test_standard_readable_instance_is_device() -> None:
    motor = _SimpleMotor("m")
    assert isinstance(motor, Device)


# ---------------------------------------------------------------------------
# numpy-array signal via soft_signal_r_and_setter
# ---------------------------------------------------------------------------


async def test_array_signal_setter_fires_subscriber() -> None:
    sig, setter = soft_signal_r_and_setter(
        np.ndarray, initial_value=np.zeros((4, 4)), name="frame"
    )
    await sig.connect(mock=False)
    frames: list[np.ndarray] = []
    sig.subscribe(lambda reading: frames.append(next(iter(reading.values()))["value"]))
    new_frame = np.ones((4, 4))
    setter(new_frame)
    assert len(frames) >= 1
    np.testing.assert_array_equal(frames[-1], new_frame)
