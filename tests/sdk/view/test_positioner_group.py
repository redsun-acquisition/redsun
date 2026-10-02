"""Tests for one device's controls in the positioner view."""

from __future__ import annotations

from typing import TypeVar

import pytest
from qtpy import QtCore, QtGui, QtWidgets

from redsun.presenter import AxisInfo
from redsun.view.qt.builtins import PositionerGroup

pytestmark = pytest.mark.qt

T = TypeVar("T", bound=QtCore.QObject)

AXES = {
    "x": AxisInfo(position=12.345, units="um", precision=3, stoppable=True),
    "theta": AxisInfo(position=0.5, units=None, precision=None),
}


@pytest.fixture
def group(qapp: QtWidgets.QApplication) -> PositionerGroup:
    return PositionerGroup(
        "stage", AXES, steps=(0.1, 1.0, 10.0), repeat_delay=100, repeat_interval=50
    )


def child(parent: QtCore.QObject, kind: type[T], name: str) -> T:
    """Return the child of *parent* of type *kind* named *name*."""
    found = parent.findChild(kind, name)
    assert found is not None
    return found


def press(widget: QtWidgets.QWidget, key: QtCore.Qt.Key, text: str = "") -> None:
    """Send *widget* a press and release of *key*."""
    for kind in (QtCore.QEvent.Type.KeyPress, QtCore.QEvent.Type.KeyRelease):
        event = QtGui.QKeyEvent(kind, key, QtCore.Qt.KeyboardModifier.NoModifier, text)
        QtWidgets.QApplication.sendEvent(widget, event)


def test_each_axis_shows_its_position_with_its_precision(
    group: PositionerGroup,
) -> None:
    """Show each readback with its own decimals, two without a precision."""
    assert child(group, QtWidgets.QLabel, "readback:x").text() == "12.345"
    assert child(group, QtWidgets.QLabel, "readback:theta").text() == "0.50"

    group.set_readback("x", 1.0)

    assert child(group, QtWidgets.QLabel, "readback:x").text() == "1.000"
    assert group.positions() == {"x": 1.0, "theta": 0.5}


@pytest.mark.parametrize(("button", "sign"), [("plus", 1.0), ("minus", -1.0)])
def test_a_step_button_moves_by_the_chosen_step(
    group: PositionerGroup, button: str, sign: float
) -> None:
    """Emit a step of the chosen size, signed by the button."""
    steps: list[tuple[str, str, float]] = []
    group.sig_move.connect(lambda *args: steps.append(args))
    child(group, QtWidgets.QComboBox, "step:x").setCurrentText("10")

    child(group, QtWidgets.QPushButton, f"{button}:x").pressed.emit()

    assert steps == [("stage", "x", sign * 10.0)]


def test_a_step_box_left_without_a_number_keeps_the_last_step(
    group: PositionerGroup,
) -> None:
    """Step by the last valid size when the step box holds no number."""
    steps: list[float] = []
    group.sig_move.connect(lambda device, axis, delta: steps.append(delta))
    box = child(group, QtWidgets.QComboBox, "step:x")
    box.setCurrentText("0.1")
    child(group, QtWidgets.QPushButton, "plus:x").pressed.emit()
    box.setCurrentText("")

    child(group, QtWidgets.QPushButton, "plus:x").pressed.emit()

    assert steps == [0.1, 0.1]


def test_arrow_keys_step_the_focused_axis(group: PositionerGroup) -> None:
    """Step the axis whose row has focus with Left and Right."""
    steps: list[float] = []
    group.sig_move.connect(lambda device, axis, delta: steps.append(delta))
    row = child(group, QtWidgets.QLabel, "readback:theta").parentWidget()
    assert row is not None

    press(row, QtCore.Qt.Key.Key_Right)
    press(row, QtCore.Qt.Key.Key_Left)

    assert steps == [1.0, -1.0]


def test_enter_in_go_to_moves_the_axis_there(group: PositionerGroup) -> None:
    """Emit a go-to for the axis when Enter is pressed in its field."""
    targets: list[tuple[str, dict[str, float]]] = []
    group.sig_move_to.connect(lambda *args: targets.append(args))
    field = child(group, QtWidgets.QLineEdit, "goto:x")
    field.setText("100.5")

    press(field, QtCore.Qt.Key.Key_Return)
    child(group, QtWidgets.QPushButton, "go:x").click()

    assert targets == [("stage", {"x": 100.5})] * 2


def test_the_state_shows_a_move_and_a_failure(group: PositionerGroup) -> None:
    """Show moving during a move, keep a failure after it, clear it at the next."""
    state = child(group, QtWidgets.QLabel, "state")

    group.set_moving(True)
    assert state.text() == "moving"
    group.set_failed("out of range")
    group.set_moving(False)
    assert (state.text(), state.toolTip()) == ("failed", "out of range")
    group.set_moving(True)
    assert (state.text(), state.toolTip()) == ("moving", "")


def test_a_locked_device_keeps_its_readbacks_and_loses_its_controls(
    group: PositionerGroup,
) -> None:
    """Disable steps, go-to and save while locked, and keep the readbacks."""
    group.set_locked(True)
    group.set_readback("x", 3.0)

    assert not child(group, QtWidgets.QPushButton, "plus:x").isEnabled()
    assert not child(group, QtWidgets.QLineEdit, "goto:x").isEnabled()
    assert not child(group, QtWidgets.QPushButton, "save").isEnabled()
    assert not child(group, QtWidgets.QPushButton, "stop").isEnabled()
    assert child(group, QtWidgets.QLabel, "readback:x").isEnabled()
    assert child(group, QtWidgets.QLabel, "readback:x").text() == "3.000"


def test_stop_is_offered_only_for_a_stoppable_device(
    qapp: QtWidgets.QApplication,
) -> None:
    """Show Stop for a device with a stoppable axis, and emit it when clicked."""
    stoppable = PositionerGroup(
        "a",
        {"x": AxisInfo(0.0, None, None, stoppable=True)},
        steps=(1.0,),
        repeat_delay=100,
        repeat_interval=50,
    )
    plain = PositionerGroup(
        "b",
        {"x": AxisInfo(0.0, None, None)},
        steps=(1.0,),
        repeat_delay=100,
        repeat_interval=50,
    )
    stops: list[str] = []
    stoppable.sig_stop.connect(stops.append)

    child(stoppable, QtWidgets.QPushButton, "stop").click()

    assert stops == ["a"]
    assert plain.findChild(QtWidgets.QPushButton, "stop") is None


def test_go_to_refuses_a_target_outside_the_limits(
    qapp: QtWidgets.QApplication,
) -> None:
    """Send a target inside the axis' limits and drop one outside them."""
    limited = PositionerGroup(
        "a",
        {"x": AxisInfo(0.0, "um", 2, limits=(-5.0, 5.0))},
        steps=(1.0,),
        repeat_delay=100,
        repeat_interval=50,
    )
    targets: list[tuple[str, dict[str, float]]] = []
    limited.sig_move_to.connect(lambda *args: targets.append(args))
    field = child(limited, QtWidgets.QLineEdit, "goto:x")
    go = child(limited, QtWidgets.QPushButton, "go:x")

    field.setText("9")
    go.click()
    field.setText("4")
    go.click()

    assert targets == [("a", {"x": 4.0})]
    assert "-5" in field.toolTip()


def test_the_repeat_interval_reaches_every_step_button(group: PositionerGroup) -> None:
    """Repeat every step button of the device at the interval set."""
    group.set_repeat_interval(120)

    buttons = group.findChildren(QtWidgets.QPushButton)
    assert {b.autoRepeatInterval() for b in buttons if b.autoRepeat()} == {120}
