"""Tests for the colour-scheme control every Qt session pins to its toolbar."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import pytest
from qtpy.QtGui import QGuiApplication
from qtpy.QtWidgets import QApplication, QToolBar

from redsun import Session
from redsun.qt import (
    ColorSchemeButton,
    ColorSchemeMode,
    QtSession,
)

if TYPE_CHECKING:
    from collections.abc import Callable

pytestmark = pytest.mark.qt


class PlainApp(QtSession):
    """A session asking for no colour scheme."""


class DarkApp(QtSession):
    config: ClassVar[dict[str, Any]] = {"color_scheme": "dark"}


@pytest.fixture(autouse=True)
def restore_scheme() -> Any:
    """Stop asking for a scheme, the style hints being process-wide."""
    yield
    hints = QGuiApplication.styleHints()
    if hints is not None:
        hints.unsetColorScheme()


def _control(app: QtSession) -> ColorSchemeButton:
    """Return the control the session put on its window."""
    found = app.main_window.findChildren(ColorSchemeButton)
    assert len(found) == 1
    return found[0]


def test_every_session_pins_the_control_to_a_toolbar(
    qapp: QApplication,
    build: Callable[..., QtSession],
) -> None:
    """Put the control on a toolbar of every session, even one declaring nothing."""
    app = build(PlainApp)
    control = _control(app)

    assert control.mode is ColorSchemeMode.SYSTEM
    assert control.parent() in app.main_window.findChildren(QToolBar)


def test_the_configuration_says_which_mode_to_start_in(
    qapp: QApplication,
    build: Callable[..., QtSession],
) -> None:
    """Start the control in the configured mode, not checking the scheme Qt reports."""
    # Only the mode asked for can be pinned: the offscreen platform the suite runs on
    # ignores `setColorScheme` and keeps reporting `Unknown`.
    assert _control(build(DarkApp)).mode is ColorSchemeMode.DARK


def test_clicking_cycles_system_light_dark_and_round(
    qapp: QApplication,
    build: Callable[..., QtSession],
) -> None:
    """Cycle the mode system -> light -> dark -> system, with a new glyph each time."""
    control = _control(build(PlainApp))
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


def test_the_control_is_pushed_to_the_right_edge(
    qapp: QApplication,
    build: Callable[..., QtSession],
) -> None:
    """Push the control to the right edge of its toolbar with an expanding spacer."""
    control = _control(build(PlainApp))
    bar = control.parent()
    assert isinstance(bar, QToolBar)

    spacer, pinned = (bar.widgetForAction(action) for action in bar.actions())

    assert pinned is control
    assert spacer is not None
    assert spacer.sizePolicy().horizontalPolicy() is (
        spacer.sizePolicy().Policy.Expanding
    )


def test_a_session_from_a_file_carries_it_too(
    qapp: QApplication,
    build: Callable[..., QtSession],
) -> None:
    """Read the starting mode from a session file too."""
    unbuilt = Session.from_config(
        {"session": "lab", "frontend": "qt", "color_scheme": "light"}
    )
    assert isinstance(unbuilt, QtSession)

    assert _control(build(unbuilt)).mode is ColorSchemeMode.LIGHT


def test_a_mode_the_control_does_not_offer_is_refused() -> None:
    """Refuse a configured mode the control does not offer."""

    class Sepia(QtSession):
        config: ClassVar[dict[str, Any]] = {"color_scheme": "sepia"}

    with pytest.raises(ValueError, match="sepia"):
        Sepia().build()


def test_the_control_says_it_can_be_clicked(qapp: QApplication) -> None:
    """End the control's tooltip by saying a click changes the mode."""
    assert (
        ColorSchemeButton(ColorSchemeMode.DARK).toolTip().endswith("(click to change)")
    )
