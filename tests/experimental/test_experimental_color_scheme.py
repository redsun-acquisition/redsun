"""Tests for the colour-scheme control every Qt session pins to its toolbar."""

from __future__ import annotations

from typing import Any, ClassVar

import pytest
from qtpy.QtGui import QGuiApplication
from qtpy.QtWidgets import QToolBar

from redsun.experimental import AppContainer
from redsun.experimental.containers.qt import (
    ColorSchemeButton,
    ColorSchemeMode,
    QtAppContainer,
)

pytestmark = pytest.mark.qt


class PlainApp(QtAppContainer):
    __slots__ = ()


class DarkApp(QtAppContainer):
    __slots__ = ()

    config: ClassVar[dict[str, Any]] = {"color_scheme": "dark"}


@pytest.fixture(autouse=True)
def restore_scheme(qapp: Any) -> Any:
    """Stop asking for a scheme, the style hints being process-wide."""
    yield
    hints = QGuiApplication.styleHints()
    if hints is not None:
        hints.unsetColorScheme()


def _control(app: QtAppContainer) -> ColorSchemeButton:
    """Return the control the session put on its window."""
    found = app.main_window.findChildren(ColorSchemeButton)
    assert len(found) == 1
    return found[0]


def test_every_session_pins_the_control_to_a_toolbar(qapp: Any) -> None:
    """It is part of the session, so a session declaring nothing still has it."""
    app = PlainApp().build()
    try:
        control = _control(app)
        assert control.mode is ColorSchemeMode.SYSTEM
        assert control.parent() in app.main_window.findChildren(QToolBar)
    finally:
        app.shutdown()


def test_the_configuration_says_which_mode_to_start_in(qapp: Any) -> None:
    """A session overrides the platform's own setting only when it asks to.

    The scheme Qt reports is not asserted: the offscreen platform the suite
    runs on ignores ``setColorScheme`` and keeps reporting ``Unknown``.
    """
    app = DarkApp().build()
    try:
        assert _control(app).mode is ColorSchemeMode.DARK
    finally:
        app.shutdown()


def test_clicking_cycles_system_light_dark_and_round(qapp: Any) -> None:
    """One button reaches all three, which is what the glyph has to keep up with."""
    app = PlainApp().build()
    try:
        control = _control(app)
        seen = []
        for _ in range(4):
            seen.append((control.mode, control.text()))
            control.click()
        assert [mode for mode, _ in seen] == [
            ColorSchemeMode.SYSTEM,
            ColorSchemeMode.LIGHT,
            ColorSchemeMode.DARK,
            ColorSchemeMode.SYSTEM,
        ]
        assert len({glyph for _, glyph in seen[:3]}) == 3
    finally:
        app.shutdown()


def test_the_control_is_pushed_to_the_right_edge(qapp: Any) -> None:
    """An expanding spacer before it is what pins it, so the toolbar holds two."""
    app = PlainApp().build()
    try:
        control = _control(app)
        bar = control.parent()
        assert isinstance(bar, QToolBar)
        spacer, pinned = (bar.widgetForAction(action) for action in bar.actions())
        assert pinned is control
        assert spacer is not None
        assert spacer.sizePolicy().horizontalPolicy() is (
            spacer.sizePolicy().Policy.Expanding
        )
    finally:
        app.shutdown()


def test_a_session_from_a_file_carries_it_too(qapp: Any) -> None:
    """The mode is an ordinary configuration key, so a file may set it."""
    app = AppContainer.from_config({"frontend": "pyqt", "color_scheme": "light"})
    assert isinstance(app, QtAppContainer)
    app.build()
    try:
        assert _control(app).mode is ColorSchemeMode.LIGHT
    finally:
        app.shutdown()


def test_a_mode_the_control_does_not_offer_is_refused(qapp: Any) -> None:
    """The mode comes from a configuration file, so it is checked."""

    class Sepia(QtAppContainer):
        __slots__ = ()

        config: ClassVar[dict[str, Any]] = {"color_scheme": "sepia"}

    with pytest.raises(ValueError, match="sepia"):
        Sepia().build()


def test_the_glyph_shows_the_mode_asked_for(qapp: Any) -> None:
    """It tracks the mode, not the scheme, so ``system`` stays right."""
    control = ColorSchemeButton(ColorSchemeMode.DARK)
    assert control.mode is ColorSchemeMode.DARK
    assert control.toolTip().endswith("(click to change)")
