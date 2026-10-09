"""Tests for the light view."""

from __future__ import annotations

import pytest
from qtpy import QtCore, QtWidgets

from redsun import Settings
from redsun.utils.devices import Configuration, LightInfo, Readback
from redsun.view.qt.builtins import LightGroup, LightView
from tests.sdk.view.helpers import child, press

pytestmark = pytest.mark.qt

LIGHTS = {
    "laser": LightInfo(False, Readback(10.0, "mW", 1, (0.0, 100.0))),
    "led": LightInfo(True),
    "lamp": LightInfo(False, Readback(5.0, "%", 0)),
}


class Lights:
    """Describes three lights, as a light presenter would."""

    lights = LIGHTS
    configuration = Configuration(descriptors={}, readings={}, writable={})


def make_view(
    settings: Settings, parent: QtWidgets.QWidget, *, dragging: bool = False
) -> LightView:
    """Build a light view on three lights, in *parent*."""
    view = LightView("lights_view", parent, write_while_dragging=dragging)
    view.setup(Lights(), settings)
    return view


def group(view: LightView, device: str) -> LightGroup:
    """Return the group of *device* in *view*."""
    found = [g for g in view.findChildren(LightGroup) if g.title() == device]
    assert len(found) == 1
    return found[0]


def test_the_toggle_asks_and_follows_the_readback(
    parent: QtWidgets.QWidget, settings: Settings
) -> None:
    """Ask for the other state on a click, and show only what the light reads back."""
    view = make_view(settings, parent)
    asked: list[tuple[str, bool]] = []
    view.sig_enabled.connect(lambda *args: asked.append(args))
    toggle = child(group(view, "laser"), QtWidgets.QAbstractButton, "toggle")

    toggle.click()
    before = (toggle.isChecked(), toggle.toolTip(), toggle.text())
    view.update_enabled("laser", True)

    assert asked == [("laser", True)]
    assert before == (False, "laser is off", "")
    assert (toggle.isChecked(), toggle.toolTip(), toggle.text()) == (
        True,
        "laser is on",
        "",
    )


def test_a_slider_writes_on_release_and_the_field_on_enter(
    parent: QtWidgets.QWidget, settings: Settings
) -> None:
    """Write the intensity when the slider is let go and when Enter is pressed."""
    view = make_view(settings, parent)
    asked: list[tuple[str, float]] = []
    view.sig_intensity.connect(lambda *args: asked.append(args))
    laser = group(view, "laser")
    slider = child(laser, QtWidgets.QSlider, "slider")
    field = child(laser, QtWidgets.QDoubleSpinBox, "intensity")

    slider.setSliderDown(True)
    slider.setValue(slider.maximum() // 2)
    during = list(asked)
    slider.setSliderDown(False)
    field.selectAll()
    press(field, "2", "5")
    typed = list(asked)
    press(field, QtCore.Qt.Key.Key_Return)

    assert during == []
    assert typed == [("laser", 50.0)]
    assert asked == [("laser", 50.0), ("laser", 25.0)]


def test_writing_while_dragging_is_throttled(
    parent: QtWidgets.QWidget, settings: Settings
) -> None:
    """Write during a drag at most every 100 ms, with the last value written last."""
    view = make_view(settings, parent, dragging=True)
    asked: list[tuple[str, float]] = []
    view.sig_intensity.connect(lambda *args: asked.append(args))
    slider = child(group(view, "laser"), QtWidgets.QSlider, "slider")

    slider.setSliderDown(True)
    for step in range(2, 7):
        slider.setValue(step * 100)
    first = list(asked)
    deadline = QtCore.QDeadlineTimer(2000)
    while asked[-1] != ("laser", 60.0) and not deadline.hasExpired():
        QtWidgets.QApplication.processEvents()
    dragged = list(asked)
    slider.setSliderDown(False)

    assert first == [("laser", 20.0)]
    assert dragged == [("laser", 20.0), ("laser", 60.0)]


def test_a_readback_waits_while_the_user_drags(
    parent: QtWidgets.QWidget, settings: Settings
) -> None:
    """Keep the slider where the user holds it, and apply the readback after."""
    view = make_view(settings, parent)
    laser = group(view, "laser")
    slider = child(laser, QtWidgets.QSlider, "slider")
    field = child(laser, QtWidgets.QDoubleSpinBox, "intensity")

    slider.setSliderDown(True)
    slider.setValue(300)
    view.update_intensity("laser", 80.0)
    held = field.value()
    slider.setSliderDown(False)
    view.update_intensity("laser", 80.0)

    assert held == pytest.approx(30.0)
    assert field.value() == pytest.approx(80.0)


def test_a_light_without_limits_has_no_slider(
    parent: QtWidgets.QWidget, settings: Settings
) -> None:
    """Offer only the number field for a light whose intensity has no range."""
    lamp = group(make_view(settings, parent), "lamp")

    assert lamp.findChild(QtWidgets.QSlider) is None
    assert child(lamp, QtWidgets.QDoubleSpinBox, "intensity").value() == 5.0


def test_an_on_off_light_has_no_intensity(
    parent: QtWidgets.QWidget, settings: Settings
) -> None:
    """Show only the toggle for a light without intensity."""
    led = group(make_view(settings, parent), "led")

    assert led.findChild(QtWidgets.QDoubleSpinBox) is None
    assert child(led, QtWidgets.QAbstractButton, "toggle").isChecked()


def test_the_dragging_choice_is_kept_between_sessions(
    parent: QtWidgets.QWidget, settings: Settings
) -> None:
    """Keep the Advanced tab's choice, over the keyword, in a later session."""
    first = make_view(settings, parent)
    child(first, QtWidgets.QCheckBox, "write-while-dragging").setChecked(True)

    later = make_view(settings, parent, dragging=False)

    assert child(later, QtWidgets.QCheckBox, "write-while-dragging").isChecked()


def test_a_held_light_cannot_be_used_until_released(
    parent: QtWidgets.QWidget, settings: Settings
) -> None:
    """Disable a held light's controls, and enable them again after."""
    view = make_view(settings, parent)
    toggle = child(group(view, "laser"), QtWidgets.QAbstractButton, "toggle")

    view.set_locked(frozenset({"laser"}))
    locked = toggle.isEnabled()
    view.set_locked(frozenset())

    assert (locked, toggle.isEnabled()) == (False, True)


def test_leaving_the_field_untouched_writes_nothing_and_shows_the_readback(
    parent: QtWidgets.QWidget, settings: Settings
) -> None:
    """Write nothing when the field loses focus unchanged, and show what came meanwhile."""
    view = make_view(settings, parent)
    asked: list[tuple[str, float]] = []
    view.sig_intensity.connect(lambda *args: asked.append(args))
    field = child(group(view, "laser"), QtWidgets.QDoubleSpinBox, "intensity")
    edit = field.lineEdit()
    assert edit is not None

    edit.textEdited.emit(edit.text())
    view.update_intensity("laser", 70.0)
    field.editingFinished.emit()

    assert asked == []
    assert field.value() == pytest.approx(70.0)


def test_a_failed_write_shows_the_intensity_read_back(
    parent: QtWidgets.QWidget, settings: Settings
) -> None:
    """Show what the light reads back, not what was asked, once a write fails."""
    view = make_view(settings, parent)
    laser = group(view, "laser")
    slider = child(laser, QtWidgets.QSlider, "slider")
    field = child(laser, QtWidgets.QDoubleSpinBox, "intensity")

    view.update_intensity("laser", 80.0)
    slider.setSliderDown(True)
    slider.setValue(300)
    slider.setSliderDown(False)
    view.set_failed("laser", "TimeoutError")

    assert field.value() == pytest.approx(80.0)
    assert slider.value() == 800


def test_the_slider_reaches_the_top_of_a_wide_finely_resolved_range(
    qapp: QtWidgets.QApplication,
) -> None:
    """Reach the top of a wide range with the slider of a finely resolved intensity."""
    light = LightGroup(
        "laser",
        LightInfo(False, Readback(1.0, "mW", 9, (0.0, 5000.0))),
        write_while_dragging=False,
    )

    slider = child(light, QtWidgets.QSlider, "slider")
    field = child(light, QtWidgets.QDoubleSpinBox, "intensity")

    slider.setValue(slider.maximum())

    assert field.value() == pytest.approx(5000.0)
    assert field.decimals() == 9


def test_the_state_line_shows_only_while_a_failure_stands(
    parent: QtWidgets.QWidget, settings: Settings
) -> None:
    """Hide the state line until a write fails, and again once the light is used."""
    view = make_view(settings, parent)
    laser = group(view, "laser")
    state = child(laser, QtWidgets.QLabel, "state")
    hidden_at_first = state.isHidden()

    view.set_failed("laser", "TimeoutError")
    shown = not state.isHidden()
    child(laser, QtWidgets.QAbstractButton, "toggle").click()

    assert (hidden_at_first, shown, state.isHidden()) == (True, True, True)
