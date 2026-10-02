"""Tests for the positioner view."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, TypeVar

import pytest
from qtpy import QtCore, QtGui, QtWidgets
from superqt import QLabeledSlider

from redsun import Settings
from redsun.presenter import AxisInfo
from redsun.view.qt.builtins import PositionerGroup, PositionerView
from redsun.view.qt.treeview import DescriptorTreeView

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.qt

T = TypeVar("T", bound=QtCore.QObject)

AXES = {
    "stage": {"x": AxisInfo(0.0, "um", 3), "theta": AxisInfo(0.0, "deg", 1)},
    "focus": {"focus": AxisInfo(52.1, "um", 2)},
}


class Positioner:
    """Describes two devices, as a positioner presenter would."""

    def axes(self) -> dict[str, dict[str, AxisInfo]]:
        return AXES

    def configuration(self) -> tuple[dict[str, Any], dict[str, Any]]:
        descriptors = {
            "stage-axis-x-velocity": {
                "source": "soft://v",
                "dtype": "number",
                "shape": [],
            },
        }
        readings = {"stage-axis-x-velocity": {"value": 1.0, "timestamp": 0.0}}
        return descriptors, readings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(tmp_path / "session.json")


@pytest.fixture
def parent(qapp: QtWidgets.QApplication) -> QtWidgets.QWidget:
    return QtWidgets.QWidget()


def make_view(
    settings: Settings, parent: QtWidgets.QWidget, repeat_interval: int = 50
) -> PositionerView:
    """Build a positioner view on two devices, in *parent*."""
    view = PositionerView("positioner", parent, repeat_interval=repeat_interval)
    view.setup(Positioner(), settings)
    return view


def child(parent: QtCore.QObject, kind: type[T], name: str = "") -> T:
    """Return the child of *parent* of type *kind*, named *name* when given."""
    found = parent.findChild(kind, name) if name else parent.findChild(kind)
    assert found is not None
    return found


def group(view: PositionerView, device: str) -> PositionerGroup:
    """Return the group of *device* in *view*."""
    found = [g for g in view.findChildren(PositionerGroup) if g.title() == device]
    assert len(found) == 1
    return found[0]


def type_into(edit: QtWidgets.QLineEdit, text: str) -> None:
    """Replace the text of *edit* by typing *text*, then press Enter."""
    edit.selectAll()
    keys = [(0, char) for char in text] + [(QtCore.Qt.Key.Key_Return, "")]
    for key, char in keys:
        for kind in (QtCore.QEvent.Type.KeyPress, QtCore.QEvent.Type.KeyRelease):
            event = QtGui.QKeyEvent(
                kind, key, QtCore.Qt.KeyboardModifier.NoModifier, char
            )
            QtWidgets.QApplication.sendEvent(edit, event)


def test_each_device_gets_a_group_whose_requests_the_view_sends(
    parent: QtWidgets.QWidget, settings: Settings
) -> None:
    """Build a group per device and send its steps and go-tos on."""
    view = make_view(settings, parent)
    moves: list[object] = []
    view.sig_move.connect(lambda *args: moves.append(args))
    view.sig_move_to.connect(lambda *args: moves.append(args))

    group(view, "stage").sig_move.emit("stage", "x", 1.0)
    group(view, "focus").sig_move_to.emit("focus", {"focus": 50.0})

    assert {g.title() for g in view.findChildren(PositionerGroup)} == {"stage", "focus"}
    assert moves == [("stage", "x", 1.0), ("focus", {"focus": 50.0})]


def test_slots_reach_the_group_of_their_device(
    parent: QtWidgets.QWidget, settings: Settings
) -> None:
    """Pass readbacks, states and locks to the group of each device."""
    view = make_view(settings, parent)

    view.update_readback("stage", "x", 4.0)
    view.set_moving("focus", True)
    view.set_failed("stage", "out of range")
    view.set_locked(frozenset({"focus"}))

    assert group(view, "stage").positions()["x"] == 4.0
    assert child(group(view, "focus"), QtWidgets.QLabel, "state").text() == "moving"
    assert child(group(view, "stage"), QtWidgets.QLabel, "state").text() == "failed"
    assert not child(group(view, "focus"), QtWidgets.QPushButton, "save").isEnabled()
    assert child(group(view, "stage"), QtWidgets.QPushButton, "save").isEnabled()


@pytest.mark.parametrize(
    ("typed", "expected"),
    [
        pytest.param("5", 10, id="below"),
        pytest.param("400", 300, id="above"),
        pytest.param("150", 150, id="inside"),
    ],
)
def test_a_typed_repeat_interval_stays_in_range_and_is_kept(
    parent: QtWidgets.QWidget, settings: Settings, typed: str, expected: int
) -> None:
    """Clamp a typed repeat interval to 10-300 ms, apply it and keep it."""
    view = make_view(settings, parent)
    slider = child(view, QLabeledSlider)

    type_into(child(slider, QtWidgets.QLineEdit), typed)

    plus = child(group(view, "stage"), QtWidgets.QPushButton, "plus:x")
    assert slider.value() == expected
    assert plus.autoRepeatInterval() == expected
    assert child(make_view(settings, parent), QLabeledSlider).value() == expected


def test_a_configuration_edit_is_sent_on(
    parent: QtWidgets.QWidget, settings: Settings
) -> None:
    """Send an edit of the configuration tree as a key and value."""
    view = make_view(settings, parent)
    sent: list[tuple[str, object]] = []
    view.sig_configure.connect(lambda *args: sent.append(args))
    stops: list[str] = []
    view.sig_stop.connect(stops.append)

    child(view, DescriptorTreeView).sig_property_changed.emit(
        "stage", "axis-x-velocity", 2.0
    )
    view.update_configuration("stage-axis-x-velocity", 2.0)
    group(view, "stage").sig_stop.emit("stage")

    assert sent == [("stage-axis-x-velocity", 2.0)]
    assert stops == ["stage"]


def test_the_repeat_interval_defaults_to_the_keyword(
    parent: QtWidgets.QWidget, settings: Settings
) -> None:
    """Start at the keyword's interval when the settings hold none."""
    view = make_view(settings, parent, repeat_interval=80)

    assert child(view, QLabeledSlider).value() == 80
