"""Tests for the light built-ins in a session."""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, ClassVar

import pytest
from qtpy import QtWidgets

from redsun import AsDevice, AsPresenter, AsView, Link
from redsun.presenter import LightPresenter
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


def test_a_light_switched_from_the_view_comes_back_switched_on(
    qapp: QtWidgets.QApplication,
    build: BuildSession,
    wait_until: Callable[..., bool],
) -> None:
    """Switch a light on from the view and show the state it reads back."""
    session = build(LightLab)
    laser = next(
        group
        for group in session.lights_view.findChildren(LightGroup)
        if group.title() == "laser"
    )
    toggle = laser.findChild(QtWidgets.QPushButton, "toggle")
    assert toggle is not None

    toggle.click()

    assert wait_until(toggle.isChecked)
