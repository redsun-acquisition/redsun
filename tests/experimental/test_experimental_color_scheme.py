"""Tests for the colour-scheme control every Qt session pins to its toolbar."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import pytest
from qtpy.QtGui import QGuiApplication
from qtpy.QtWidgets import QApplication, QToolBar

from redsun.experimental import Session
from redsun.experimental.session.qt import (
    ColorSchemeButton,
    ColorSchemeMode,
    QtSession,
)

if TYPE_CHECKING:
    from collections.abc import Callable

pytestmark = pytest.mark.qt


class PlainApp(QtSession):
    __slots__ = ()


class DarkApp(QtSession):
    __slots__ = ()

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
    """It is part of the session, so a session declaring nothing still has it."""
    app = build(PlainApp)
    control = _control(app)

    assert control.mode is ColorSchemeMode.SYSTEM
    assert control.parent() in app.main_window.findChildren(QToolBar)


def test_the_configuration_says_which_mode_to_start_in(
    qapp: QApplication,
    build: Callable[..., QtSession],
) -> None:
    """The scheme Qt reports is not asserted.

    The offscreen platform the suite runs on ignores ``setColorScheme`` and
    keeps reporting ``Unknown``, so only the mode asked for can be pinned.
    """
    assert _control(build(DarkApp)).mode is ColorSchemeMode.DARK


def test_clicking_cycles_system_light_dark_and_round(
    qapp: QApplication,
    build: Callable[..., QtSession],
) -> None:
    """One button reaches all three, which the glyph has to keep up with."""
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
    """An expanding spacer before it is what pins it, so the toolbar holds two."""
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
    """The mode is an ordinary configuration key, so a file may set it."""
    unbuilt = Session.from_config({"frontend": "pyqt", "color_scheme": "light"})
    assert isinstance(unbuilt, QtSession)

    assert _control(build(unbuilt)).mode is ColorSchemeMode.LIGHT


def test_a_mode_the_control_does_not_offer_is_refused() -> None:
    """The mode comes from a configuration file, so it is checked."""

    class Sepia(QtSession):
        __slots__ = ()

        config: ClassVar[dict[str, Any]] = {"color_scheme": "sepia"}

    with pytest.raises(ValueError, match="sepia"):
        Sepia().build()


def test_the_control_says_it_can_be_clicked() -> None:
    assert (
        ColorSchemeButton(ColorSchemeMode.DARK).toolTip().endswith("(click to change)")
    )
