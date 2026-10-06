"""Tests for the light built-ins in a session."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, ClassVar

import pytest
from qtpy import QtWidgets

from redsun import AsDevice, AsPresenter, AsView, Link
from redsun.presenter import AcquisitionPresenter, LightPresenter
from redsun.qt import QtSession
from redsun.view.qt.builtins import LightGroup, LightView
from tests.sdk.mocks import DimmerLight, SoftLight

if TYPE_CHECKING:
    from collections.abc import Callable

    from redsun.testing import BuildSession

pytestmark = pytest.mark.qt


class LightLab(QtSession):
    config: ClassVar[dict[str, Any]] = {"session": "light-lab"}

    laser: AsDevice[DimmerLight]
    led: AsDevice[SoftLight]
    lights: AsPresenter[LightPresenter]
    lights_view: AsView[LightView]

    def wire(self) -> Iterator[Link]:
        yield self.lights_view.sig_enabled, self.lights.set_enabled
        yield self.lights_view.sig_intensity, self.lights.set_intensity
        yield self.lights_view.sig_configure, self.lights.configure
        yield self.lights.sig_enabled, self.lights_view.update_enabled
        yield self.lights.sig_intensity, self.lights_view.update_intensity
        yield self.lights.sig_failed, self.lights_view.set_failed
        yield self.lights.sig_configuration, self.lights_view.update_configuration


class PairedLightLab(QtSession):
    config: ClassVar[dict[str, Any]] = {
        "session": "light-lab-paired",
        "pairs": [["lights_view", "lights"], ["acquisition", "lights_view"]],
    }

    laser: AsDevice[DimmerLight]
    led: AsDevice[SoftLight]
    acquisition: AsPresenter[AcquisitionPresenter]
    lights: AsPresenter[LightPresenter]
    lights_view: AsView[LightView]


def laser_toggle(session: QtSession) -> QtWidgets.QPushButton:
    """Return the laser's on/off button."""
    view = session.views["lights_view"]
    assert isinstance(view, LightView)
    laser = next(
        group for group in view.findChildren(LightGroup) if group.title() == "laser"
    )
    toggle = laser.findChild(QtWidgets.QPushButton, "toggle")
    assert toggle is not None
    return toggle


@pytest.mark.parametrize("lab", [LightLab, PairedLightLab])
def test_a_light_switched_from_the_view_comes_back_switched_on(
    qapp: QtWidgets.QApplication,
    build: BuildSession,
    wait_until: Callable[..., bool],
    lab: type[QtSession],
) -> None:
    """Switch a light on from the view, wired by hand or paired, and show its state."""
    toggle = laser_toggle(build(lab))

    toggle.click()

    assert wait_until(toggle.isChecked)


def test_pairing_the_acquisition_presenter_with_the_view_passes_on_locks(
    qapp: QtWidgets.QApplication,
    build: BuildSession,
    wait_until: Callable[..., bool],
) -> None:
    """Disable a light the engine locks, through the pairing with the acquisition presenter."""
    session = build(PairedLightLab)
    toggle = laser_toggle(session)

    session.acquisition.sig_locks_changed.emit(frozenset({"laser"}))

    assert wait_until(lambda: not toggle.isEnabled())
