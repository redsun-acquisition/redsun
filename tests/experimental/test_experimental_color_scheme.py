"""Tests for the colour-scheme control every Qt session pins to its toolbar."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

import pytest
from qtpy.QtGui import QGuiApplication
from qtpy.QtWidgets import QToolBar

from redsun.experimental import AppContainer
from redsun.experimental.containers.qt import (
    ColorSchemeButton,
    ColorSchemeMode,
    QtAppContainer,
)

if TYPE_CHECKING:
    from collections.abc import Callable

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


def test_every_session_pins_the_control_to_a_toolbar(
    qapp: Any, build: Callable[..., Any]
) -> None:
    """It is part of the session, so a session declaring nothing still has it."""
    app = build(PlainApp)
    control = _control(app)

    assert control.mode is ColorSchemeMode.SYSTEM
    assert control.parent() in app.main_window.findChildren(QToolBar)


def test_the_configuration_says_which_mode_to_start_in(
    qapp: Any, build: Callable[..., Any]
) -> None:
    """The scheme Qt reports is not asserted.

    The offscreen platform the suite runs on ignores ``setColorScheme`` and
    keeps reporting ``Unknown``, so only the mode asked for can be pinned.
    """
    assert _control(build(DarkApp)).mode is ColorSchemeMode.DARK


def test_clicking_cycles_system_light_dark_and_round(
    qapp: Any, build: Callable[..., Any]
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
    qapp: Any, build: Callable[..., Any]
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
    qapp: Any, build: Callable[..., Any]
) -> None:
    """The mode is an ordinary configuration key, so a file may set it."""
    unbuilt = AppContainer.from_config({"frontend": "pyqt", "color_scheme": "light"})
    assert isinstance(unbuilt, QtAppContainer)

    assert _control(build(unbuilt)).mode is ColorSchemeMode.LIGHT


def test_a_mode_the_control_does_not_offer_is_refused(qapp: Any) -> None:
    """The mode comes from a configuration file, so it is checked."""

    class Sepia(QtAppContainer):
        __slots__ = ()

        config: ClassVar[dict[str, Any]] = {"color_scheme": "sepia"}

    with pytest.raises(ValueError, match="sepia"):
        Sepia().build()


def test_the_control_says_it_can_be_clicked(qapp: Any) -> None:
    assert (
        ColorSchemeButton(ColorSchemeMode.DARK).toolTip().endswith("(click to change)")
    )
