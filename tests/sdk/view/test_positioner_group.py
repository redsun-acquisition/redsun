"""Tests for one device's controls in the positioner view."""

from __future__ import annotations

from itertools import pairwise
from typing import TypeVar

import pytest
from qtpy import QtCore, QtGui, QtWidgets

from redsun.utils.devices import AxisInfo, Readback
from redsun.view.qt.builtins import PositionerGroup

pytestmark = pytest.mark.qt

T = TypeVar("T", bound=QtCore.QObject)

AXES = {
    "x": AxisInfo(Readback(12.345, "um", 3), stoppable=True),
    "theta": AxisInfo(Readback(0.5)),
}


@pytest.fixture
def group(qapp: QtWidgets.QApplication) -> PositionerGroup:
    return PositionerGroup(
        "stage", AXES, steps=(0.1, 1.0, 10.0), repeat_delay=100, repeat_interval=50
    )


def spin_group(qapp: QtWidgets.QApplication) -> PositionerGroup:
    """Return a group whose step boxes are spin boxes."""
    return PositionerGroup(
        "stage",
        AXES,
        steps=(0.001, 0.1, 1.0, 10.0),
        repeat_delay=100,
        repeat_interval=50,
        step_box="spinbox",
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
    assert group.positions == {"x": 1.0, "theta": 0.5}


@pytest.mark.parametrize(("button", "sign"), [("plus", 1.0), ("minus", -1.0)])
def test_a_step_button_moves_by_the_chosen_step(
    group: PositionerGroup, button: str, sign: float
) -> None:
    """Emit a step of the chosen size, signed by the button."""
    steps: list[tuple[str, str, float]] = []
    group.sig_move.connect(lambda *args: steps.append(args))
    child(group, QtWidgets.QComboBox, "step:x").setCurrentText("10")

    child(group, QtWidgets.QAbstractButton, f"{button}:x").pressed.emit()

    assert steps == [("stage", "x", sign * 10.0)]


def test_a_step_box_left_without_a_number_keeps_the_last_step(
    group: PositionerGroup,
) -> None:
    """Step by the last valid size when the step box holds no number."""
    steps: list[float] = []
    group.sig_move.connect(lambda device, axis, delta: steps.append(delta))
    box = child(group, QtWidgets.QComboBox, "step:x")
    box.setCurrentText("0.1")
    child(group, QtWidgets.QAbstractButton, "plus:x").pressed.emit()
    box.setCurrentText("")
    child(group, QtWidgets.QAbstractButton, "plus:x").pressed.emit()
    box.setCurrentText("0")

    child(group, QtWidgets.QAbstractButton, "plus:x").pressed.emit()

    assert steps == [0.1, 0.1, 0.1]


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
    child(group, QtWidgets.QAbstractButton, "go:x").click()

    assert targets == [("stage", {"x": 100.5})] * 2


def test_the_state_shows_a_move_and_a_failure(group: PositionerGroup) -> None:
    """Show moving during a move, keep a failure after it, clear it at the next."""
    state = child(group, QtWidgets.QLabel, "state")

    group.set_moving(True)
    assert state.text() == "moving"
    group.set_failed("out of range")
    group.set_moving(False)
    assert (state.text(), state.toolTip()) == ("failed: out of range", "out of range")
    group.set_moving(True)
    assert (state.text(), state.toolTip()) == ("moving", "")


def test_a_locked_device_keeps_its_readbacks_and_loses_its_controls(
    group: PositionerGroup,
) -> None:
    """Disable steps, go-to and save while locked, and keep the readbacks."""
    group.set_locked(True)
    group.set_readback("x", 3.0)

    assert not child(group, QtWidgets.QAbstractButton, "plus:x").isEnabled()
    assert not child(group, QtWidgets.QLineEdit, "goto:x").isEnabled()
    assert not child(group, QtWidgets.QAbstractButton, "save").isEnabled()
    assert not child(group, QtWidgets.QAbstractButton, "stop").isEnabled()
    assert child(group, QtWidgets.QLabel, "readback:x").isEnabled()
    assert child(group, QtWidgets.QLabel, "readback:x").text() == "3.000"


def test_stop_is_offered_only_for_a_stoppable_device(
    qapp: QtWidgets.QApplication,
) -> None:
    """Show Stop for a device with a stoppable axis, and emit it when clicked."""
    stoppable = PositionerGroup(
        "a",
        {"x": AxisInfo(Readback(0.0), stoppable=True)},
        steps=(1.0,),
        repeat_delay=100,
        repeat_interval=50,
    )
    plain = PositionerGroup(
        "b",
        {"x": AxisInfo(Readback(0.0))},
        steps=(1.0,),
        repeat_delay=100,
        repeat_interval=50,
    )
    stops: list[str] = []
    stoppable.sig_stop.connect(stops.append)

    child(stoppable, QtWidgets.QAbstractButton, "stop").click()

    assert stops == ["a"]
    assert plain.findChild(QtWidgets.QAbstractButton, "stop") is None


def test_go_to_refuses_a_target_outside_the_limits(
    qapp: QtWidgets.QApplication,
) -> None:
    """Send a target inside the axis' limits and drop one outside them."""
    limited = PositionerGroup(
        "a",
        {"x": AxisInfo(Readback(0.0, "um", 2, (-5.0, 5.0)))},
        steps=(1.0,),
        repeat_delay=100,
        repeat_interval=50,
    )
    targets: list[tuple[str, dict[str, float]]] = []
    limited.sig_move_to.connect(lambda *args: targets.append(args))
    field = child(limited, QtWidgets.QLineEdit, "goto:x")
    go = child(limited, QtWidgets.QAbstractButton, "go:x")

    field.setText("9")
    go.click()
    field.setText("4")
    go.click()

    assert targets == [("a", {"x": 4.0})]
    assert "-5" in field.toolTip()


def test_arrow_keys_do_not_step_a_locked_device(group: PositionerGroup) -> None:
    """Ignore Left and Right on a row of a locked device."""
    steps: list[float] = []
    group.sig_move.connect(lambda device, axis, delta: steps.append(delta))
    row = child(group, QtWidgets.QLabel, "readback:x").parentWidget()
    assert row is not None

    group.set_locked(True)
    press(row, QtCore.Qt.Key.Key_Right)

    assert steps == []


def test_the_repeat_interval_reaches_every_step_button(group: PositionerGroup) -> None:
    """Repeat every step button of the device at the interval set."""
    group.set_repeat_interval(120)

    buttons = group.findChildren(QtWidgets.QAbstractButton)
    assert {b.autoRepeatInterval() for b in buttons if b.autoRepeat()} == {120}


def test_arrow_keys_step_while_a_step_button_has_focus(group: PositionerGroup) -> None:
    """Step with Right and Left while a step button has focus, as after a click."""
    steps: list[float] = []
    group.sig_move.connect(lambda device, axis, delta: steps.append(delta))
    plus = child(group, QtWidgets.QAbstractButton, "plus:x")

    press(plus, QtCore.Qt.Key.Key_Right)
    press(plus, QtCore.Qt.Key.Key_Left)

    assert steps == [1.0, -1.0]


def test_every_control_has_a_name_a_screen_reader_can_say(
    group: PositionerGroup,
) -> None:
    """Name every button, field and box of the group for assistive tools."""
    kinds = (QtWidgets.QAbstractButton, QtWidgets.QLineEdit, QtWidgets.QComboBox)
    controls = [w for kind in kinds for w in group.findChildren(kind)]
    unnamed = [
        w.objectName()
        for w in controls
        if not w.accessibleName()
        and not isinstance(w.parentWidget(), QtWidgets.QComboBox)
    ]

    assert unnamed == []


def test_the_step_box_moves_through_its_decades(group: PositionerGroup) -> None:
    """Step by the next decade after pressing Down in the step box."""
    steps: list[float] = []
    group.sig_move.connect(lambda device, axis, delta: steps.append(delta))

    press(child(group, QtWidgets.QComboBox, "step:x"), QtCore.Qt.Key.Key_Down)
    child(group, QtWidgets.QAbstractButton, "plus:x").pressed.emit()

    assert steps == [10.0]


def test_the_go_to_field_follows_the_readback_until_a_target_is_typed(
    group: PositionerGroup,
) -> None:
    """Show the readback in the go-to field, and keep a typed target."""
    field = child(group, QtWidgets.QLineEdit, "goto:x")

    group.set_readback("x", 7.0)
    shown = field.text()
    field.setText("3")
    field.setModified(True)
    group.set_readback("x", 8.0)

    assert (shown, field.text()) == ("7.000", "3")


def test_a_refused_target_says_why(qapp: QtWidgets.QApplication) -> None:
    """Show why a target outside the limits was not sent."""
    limited = PositionerGroup(
        "a",
        {"x": AxisInfo(Readback(0.0, "um", 2, (-5.0, 5.0)))},
        steps=(1.0,),
        repeat_delay=100,
        repeat_interval=50,
    )
    child(limited, QtWidgets.QLineEdit, "goto:x").setText("9")

    child(limited, QtWidgets.QAbstractButton, "go:x").click()

    state = child(limited, QtWidgets.QLabel, "state").text()
    assert "9" in state
    assert "-5.00" in state


def test_unlocking_gives_the_controls_back(group: PositionerGroup) -> None:
    """Enable the controls again once a plan releases the device."""
    group.set_locked(True)
    group.set_locked(False)

    assert child(group, QtWidgets.QAbstractButton, "plus:x").isEnabled()
    assert child(group, QtWidgets.QAbstractButton, "save").isEnabled()


def test_the_group_fits_a_narrow_dock(group: PositionerGroup) -> None:
    """Keep the group within 150 px of frames and spacing plus 16 digits of its font."""
    digit = group.fontMetrics().horizontalAdvance("0")

    assert group.minimumSizeHint().width() <= 150 + 16 * digit


def test_a_group_without_steps_is_refused(qapp: QtWidgets.QApplication) -> None:
    """Refuse to build a group offered no step size."""
    with pytest.raises(ValueError, match="no step size"):
        PositionerGroup(
            "a",
            {"x": AxisInfo(Readback(0.0))},
            steps=(),
            repeat_delay=1,
            repeat_interval=1,
        )


def test_no_control_of_a_row_covers_another(group: PositionerGroup) -> None:
    """Lay out the controls of each row side by side, never over each other."""
    group.resize(group.minimumSizeHint())
    group.show()
    QtWidgets.QApplication.processEvents()
    for axis in ("x", "theta"):
        names = (f"minus:{axis}", f"step:{axis}", f"plus:{axis}", f"goto:{axis}")
        controls = [child(group, QtWidgets.QWidget, name) for name in names]

        for left, right in pairwise(controls):
            assert left.geometry().right() < right.geometry().left(), (
                left.objectName(),
                right.objectName(),
            )


def test_the_step_box_centres_its_size(group: PositionerGroup) -> None:
    """Centre the step size in the step box and in the sizes it lists."""
    box = child(group, QtWidgets.QComboBox, "step:x")
    edit = box.lineEdit()
    assert edit is not None
    centred = QtCore.Qt.AlignmentFlag.AlignHCenter

    assert edit.alignment() & centred
    assert all(
        box.itemData(index, QtCore.Qt.ItemDataRole.TextAlignmentRole) & centred
        for index in range(box.count())
    )


def test_a_spin_box_steps_by_the_size_it_holds(qapp: QtWidgets.QApplication) -> None:
    """Step by the size typed in a spin box, starting from the default size."""
    group = spin_group(qapp)
    steps: list[float] = []
    group.sig_move.connect(lambda device, axis, delta: steps.append(delta))
    box = child(group, QtWidgets.QDoubleSpinBox, "step:x")
    plus = child(group, QtWidgets.QAbstractButton, "plus:x")

    plus.pressed.emit()
    box.setValue(0.25)
    plus.pressed.emit()

    assert steps == [1.0, 0.25]
    assert box.alignment() & QtCore.Qt.AlignmentFlag.AlignHCenter


@pytest.mark.parametrize(
    ("typed", "kept", "shown"),
    [
        pytest.param(0.001, 0.001, "0.001", id="smallest"),
        pytest.param(0.0001, 0.001, "0.001", id="below"),
        pytest.param(50.0, 10.0, "10.000", id="above"),
    ],
)
def test_a_spin_box_keeps_to_the_steps_offered(
    qapp: QtWidgets.QApplication, typed: float, kept: float, shown: str
) -> None:
    """Keep a spin box between the smallest and largest step, written with a dot."""
    box = child(spin_group(qapp), QtWidgets.QDoubleSpinBox, "step:x")

    box.setValue(typed)

    assert (box.value(), box.text()) == (kept, shown)


def test_an_unknown_step_box_is_refused(qapp: QtWidgets.QApplication) -> None:
    """Refuse a step box that is neither a combo box nor a spin box."""
    with pytest.raises(ValueError, match="step_box"):
        PositionerGroup(
            "a",
            AXES,
            steps=(1.0,),
            repeat_delay=1,
            repeat_interval=1,
            step_box="slider",  # type: ignore[arg-type]
        )
