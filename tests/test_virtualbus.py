from types import MappingProxyType
from typing import TYPE_CHECKING, Tuple, Union

import numpy as np
import pytest
from numpy import ndarray

from redsun.toolkit.virtualbus import Signal, VirtualBus

if TYPE_CHECKING:
    from logging import LogRecord


class MockVirtualBus(VirtualBus):
    sigMyOtherSignal = Signal(int, info="My other signal")

    def __init__(self):
        super().__init__()


class BigMockVirtualBus(VirtualBus):
    """A `VirtualBus` subclass with a lot of signals."""

    sigSignal1 = Signal(str)
    sigSignal2 = Signal(int)
    sigSignal3 = Signal(str, int)
    sigSignal4 = Signal(str, int, float)
    sigSignal5 = Signal(str, int, float, dict)
    sigSignal6 = Signal(str, int, float, dict, ndarray)
    sigSignal7 = Signal(int, str, ndarray)
    sigSignal8 = Signal(str, ndarray, list)
    sigSignal9 = Signal(str, list, dict, object)
    sigSignal10 = Signal(int, list, dict)
    sigSignal11 = Signal(float, list, ndarray)
    sigSignal12 = Signal(float)
    sigSignal13 = Signal(float, float, float)
    sigSignal14 = Signal(tuple, tuple)
    sigSignal15 = Signal(dict, tuple)
    sigSignal16 = Signal(ndarray)
    sigSignal17 = Signal(ndarray, tuple, dict)
    sigSignal18 = Signal(dict)

    def __init__(self) -> None:
        super().__init__()


# Helper function to assert values considering NumPy arrays
def assert_equal(dest, expected):
    if isinstance(dest, tuple) and any(isinstance(i, np.ndarray) for i in dest):
        for d, e in zip(dest, expected):
            if isinstance(d, np.ndarray):
                assert np.array_equal(d, e)
            else:
                assert d == e
    else:
        assert dest == expected


def test_virtual_bus_signal_creation():
    """Test the creation of a `Signal` instance in a `VirtualBus` subclass."""

    dest = "start"

    def my_slot(data: str) -> None:
        nonlocal dest
        dest = data

    mock_bus = MockVirtualBus()

    assert mock_bus.sigMyOtherSignal.types == (int,)
    assert mock_bus.sigMyOtherSignal.info == "My other signal"
    assert mock_bus.signals == MappingProxyType(
        {"sigMyOtherSignal": mock_bus.sigMyOtherSignal}
    )

    mock_bus.register_signal("sigDataSignal", str)

    assert hasattr(mock_bus, "sigDataSignal")
    assert isinstance(mock_bus.sigDataSignal, Signal)

    assert hasattr(mock_bus, "sigMyOtherSignal")
    assert isinstance(mock_bus.sigMyOtherSignal, Signal)

    mock_bus.register_signal("sigDataSignal2", str, int, ndarray)
    assert hasattr(mock_bus, "sigDataSignal2")
    assert isinstance(mock_bus.sigDataSignal2, Signal)

    mock_bus.sigAttributeSignal = Signal(int)
    assert len(mock_bus.signals) == 4

    # check that sigDataSignal works
    mock_bus.sigDataSignal.connect(my_slot)
    mock_bus.sigDataSignal.emit("stop")

    assert dest == "stop"

    mock_bus.sigDataSignal.disconnect(my_slot)
    mock_bus.sigDataSignal.emit("start")

    assert dest == "stop"

    mock_bus.sigDataSignal.connect(lambda data: my_slot(data))
    mock_bus.sigDataSignal.emit("start")

    assert dest == "start"

    mock_bus.sigDataSignal.disconnect()
    mock_bus.sigDataSignal.emit("stop")

    assert dest == "start"

    # check that sigDataSignal2 works
    def my_slot2(*data: Tuple[Union[str, int, np.ndarray], ...]) -> None:
        nonlocal dest
        dest = data

    mock_bus.sigDataSignal2.connect(my_slot2)
    mock_bus.sigDataSignal2.emit("stop", 42, np.array([1, 2, 3]))

    assert_equal(dest, ("stop", 42, np.array([1, 2, 3])))


def test_virtual_bus_warning_signal_registration(caplog: "LogRecord"):
    """Test the warning message when registering an existing signal."""

    mock_bus = MockVirtualBus()
    mock_bus.register_signal("sigMyOtherSignal", int)
    assert "Signal sigMyOtherSignal already exists in MockVirtualBus." in caplog.text


def test_virtual_bus_fail_signal_registration():
    """Tests the failure of registering a signal with an invalid name."""

    mock_bus = MockVirtualBus()

    with pytest.raises(ValueError):
        mock_bus.register_signal("dataSignal", str)


def test_big_virtual_bus_construction():
    """Test the construction of a `BigMockVirtualBus` instance."""

    mock_bus = BigMockVirtualBus()

    # we have 18 signals numered from 1 to 18
    # in the `BigMockVirtualBus` class; the + 1 is
    # just to make the range inclusive
    for i in range(1, 18 + 1):
        assert hasattr(mock_bus, f"sigSignal{i}")
        assert isinstance(getattr(mock_bus, f"sigSignal{i}"), Signal)


def test_big_virtual_bus_signals():
    """Test the signals in a `BigMockVirtualBus` instance."""

    mock_bus = BigMockVirtualBus()

    dest = "start"

    def my_slot(
        *data: Tuple[
            Union[str, int, float, dict, np.ndarray, list, object, tuple], ...
        ],
    ) -> None:
        nonlocal dest
        if len(data) == 1:
            dest = data[0]
        else:
            dest = data

    # Test sigSignal1
    mock_bus.sigSignal1.connect(my_slot)
    mock_bus.sigSignal1.emit("stop")
    assert dest == "stop"
    mock_bus.sigSignal1.disconnect(my_slot)

    # Test sigSignal2
    mock_bus.sigSignal2.connect(my_slot)
    mock_bus.sigSignal2.emit(42)
    assert dest == 42
    mock_bus.sigSignal2.disconnect(my_slot)

    # Test sigSignal3
    mock_bus.sigSignal3.connect(my_slot)
    mock_bus.sigSignal3.emit("test", 3)
    assert dest == ("test", 3)
    mock_bus.sigSignal3.disconnect(my_slot)

    # Test sigSignal4
    mock_bus.sigSignal4.connect(my_slot)
    mock_bus.sigSignal4.emit("test", 3, 4.5)
    assert dest == ("test", 3, 4.5)
    mock_bus.sigSignal4.disconnect(my_slot)

    # Test sigSignal5
    mock_bus.sigSignal5.connect(my_slot)
    mock_bus.sigSignal5.emit("test", 3, 4.5, {"key": "value"})
    assert dest == ("test", 3, 4.5, {"key": "value"})
    mock_bus.sigSignal5.disconnect(my_slot)

    # Test sigSignal6
    mock_bus.sigSignal6.connect(my_slot)
    mock_bus.sigSignal6.emit("test", 3, 4.5, {"key": "value"}, np.array([1, 2, 3]))
    assert_equal(dest, ("test", 3, 4.5, {"key": "value"}, np.array([1, 2, 3])))
    mock_bus.sigSignal6.disconnect(my_slot)

    # Test sigSignal7
    mock_bus.sigSignal7.connect(my_slot)
    mock_bus.sigSignal7.emit(3, "test", np.array([1, 2, 3]))
    assert_equal(dest, (3, "test", np.array([1, 2, 3])))
    mock_bus.sigSignal7.disconnect(my_slot)

    # Test sigSignal8
    mock_bus.sigSignal8.connect(my_slot)
    mock_bus.sigSignal8.emit("test", np.array([1, 2, 3]), [4, 5, 6])
    assert_equal(dest, ("test", np.array([1, 2, 3]), [4, 5, 6]))
    mock_bus.sigSignal8.disconnect(my_slot)

    # Test sigSignal9
    mock_bus.sigSignal9.connect(my_slot)
    mock_bus.sigSignal9.emit("test", [1, 2, 3], {"key": "value"}, object())
    assert isinstance(dest[-1], object)
    mock_bus.sigSignal9.disconnect(my_slot)

    # Test sigSignal10
    mock_bus.sigSignal10.connect(my_slot)
    mock_bus.sigSignal10.emit(3, [1, 2, 3], {"key": "value"})
    assert dest == (3, [1, 2, 3], {"key": "value"})
    mock_bus.sigSignal10.disconnect(my_slot)

    # Test sigSignal11
    mock_bus.sigSignal11.connect(my_slot)
    mock_bus.sigSignal11.emit(4.5, [1, 2, 3], np.array([1, 2, 3]))
    assert_equal(dest, (4.5, [1, 2, 3], np.array([1, 2, 3])))
    mock_bus.sigSignal11.disconnect(my_slot)

    # Test sigSignal12
    mock_bus.sigSignal12.connect(my_slot)
    mock_bus.sigSignal12.emit(4.5)
    assert dest == 4.5
    mock_bus.sigSignal12.disconnect(my_slot)

    # Test sigSignal13
    mock_bus.sigSignal13.connect(my_slot)
    mock_bus.sigSignal13.emit(4.5, 5.5, 6.5)
    assert dest == (4.5, 5.5, 6.5)
    mock_bus.sigSignal13.disconnect(my_slot)

    # Test sigSignal14
    mock_bus.sigSignal14.connect(my_slot)
    mock_bus.sigSignal14.emit((1, 2), (3, 4))
    assert dest == ((1, 2), (3, 4))
    mock_bus.sigSignal14.disconnect(my_slot)

    # Test sigSignal15
    mock_bus.sigSignal15.connect(my_slot)
    mock_bus.sigSignal15.emit({"key": "value"}, (3, 4))
    assert dest == ({"key": "value"}, (3, 4))
    mock_bus.sigSignal15.disconnect(my_slot)

    # Test sigSignal16
    mock_bus.sigSignal16.connect(my_slot)
    mock_bus.sigSignal16.emit(np.array([1, 2, 3]))
    assert np.array_equal(dest, np.array([1, 2, 3]))
    mock_bus.sigSignal16.disconnect(my_slot)

    # Test sigSignal17
    mock_bus.sigSignal17.connect(my_slot)
    mock_bus.sigSignal17.emit(np.array([1, 2, 3]), (3, 4), {"key": "value"})
    assert_equal(dest, (np.array([1, 2, 3]), (3, 4), {"key": "value"}))
    mock_bus.sigSignal17.disconnect(my_slot)

    # Test sigSignal18
    mock_bus.sigSignal18.connect(my_slot)
    mock_bus.sigSignal18.emit({"key": "value"})
    assert dest == {"key": "value"}
    mock_bus.sigSignal18.disconnect(my_slot)
