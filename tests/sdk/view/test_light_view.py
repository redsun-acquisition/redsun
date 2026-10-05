"""Tests for the light view."""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

import pytest
from qtpy import QtCore, QtWidgets

from redsun import Settings
from redsun.utils.devices import Configuration, LightInfo
from redsun.view.qt.builtins import LightGroup, LightView

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.qt

T = TypeVar("T", bound=QtCore.QObject)

LIGHTS = {
    "laser": LightInfo(False, 10.0, "mW", 1, (0.0, 100.0)),
    "led": LightInfo(True),
    "lamp": LightInfo(False, 5.0, "%", 0),
}


class Lights:
    """Describes three lights, as a light presenter would."""

    lights = LIGHTS
    configuration = Configuration(descriptors={}, readings={}, writable={})


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(tmp_path / "session.json")


@pytest.fixture
def parent(qapp: QtWidgets.QApplication) -> QtWidgets.QWidget:
    return QtWidgets.QWidget()


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


def child(parent: QtCore.QObject, kind: type[T], name: str) -> T:
    """Return the child of *parent* of type *kind* named *name*."""
    found = parent.findChild(kind, name)
    assert found is not None
    return found


def test_the_toggle_asks_and_follows_the_readback(
    parent: QtWidgets.QWidget, settings: Settings
) -> None:
    """Ask for the other state on a click, and show only what the light reads back."""
    view = make_view(settings, parent)
    asked: list[tuple[str, bool]] = []
    view.sig_enabled.connect(lambda *args: asked.append(args))
    toggle = child(group(view, "laser"), QtWidgets.QAbstractButton, "toggle")

    toggle.click()
    before = (toggle.isChecked(), toggle.text())
    view.update_enabled("laser", True)

    assert asked == [("laser", True)]
    assert before == (False, "Off")
    assert (toggle.isChecked(), toggle.text()) == (True, "On")


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
    field.setValue(25.0)
    field.editingFinished.emit()

    assert during == []
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
    deadline = QtCore.QDeadlineTimer(150)
    while not deadline.hasExpired():
        QtWidgets.QApplication.processEvents()
    slider.setSliderDown(False)

    assert first == [("laser", 20.0)]
    assert asked[-1] == ("laser", 60.0)
    assert len(asked) < 5


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


def test_a_fine_precision_over_a_wide_range_still_builds(
    qapp: QtWidgets.QApplication,
) -> None:
    """Build the slider of an intensity with many decimals over a wide range."""
    light = LightGroup(
        "laser",
        LightInfo(False, 1.0, "mW", 9, (0.0, 5000.0)),
        write_while_dragging=False,
    )

    slider = child(light, QtWidgets.QSlider, "slider")

    assert slider.maximum() < 2**31
    assert child(light, QtWidgets.QDoubleSpinBox, "intensity").decimals() == 9
