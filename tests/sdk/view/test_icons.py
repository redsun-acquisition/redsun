"""Tests for the icons the built-in views draw from the icon font."""

from __future__ import annotations

import gc
import weakref

import pytest
from qtpy.QtCore import QSize
from qtpy.QtGui import QColor, QIcon, QPalette
from qtpy.QtWidgets import (
    QApplication,
    QComboBox,
    QPushButton,
    QStyleFactory,
    QToolButton,
)
from superqt import QCollapsible

from redsun.view.qt._icons import set_collapsible_icons, set_icon, set_item_icon

pytestmark = pytest.mark.qt

STYLES = QStyleFactory.keys()
"""The Qt styles this machine can create."""


def colours(icon: QIcon, mode: QIcon.Mode = QIcon.Mode.Normal) -> set[str]:
    """Return the opaque colours drawn in *icon* at 32 by 32."""
    image = icon.pixmap(QSize(32, 32), mode).toImage()
    return {
        image.pixelColor(x, y).name()
        for x in range(image.width())
        for y in range(image.height())
        if image.pixelColor(x, y).alpha() == 255
    }


def palette(text: str, disabled: str) -> QPalette:
    """Return a palette with *text* as button text, *disabled* when disabled."""
    result = QPalette()
    result.setColor(QPalette.ColorRole.ButtonText, QColor(text))
    result.setColor(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(disabled)
    )
    return result


def test_an_icon_replaces_the_text_and_carries_the_words(qapp: QApplication) -> None:
    """Show an icon with no text, and put the words in the tooltip and accessible name."""
    button = QPushButton("Run")

    set_icon(button, "play", "Run the plan")

    assert (button.text(), button.toolTip(), button.accessibleName()) == (
        "",
        "Run the plan",
        "Run the plan",
    )
    assert not button.icon().isNull()


def test_an_icon_is_larger_than_the_text_it_replaces(qapp: QApplication) -> None:
    """Size an icon above the button's line height, whatever the font size."""
    button = QPushButton()
    font = button.font()
    font.setPointSize(20)
    button.setFont(font)

    set_icon(button, "play", "Run the plan")

    assert button.iconSize().height() > button.fontMetrics().height()


def test_an_icon_follows_the_palette_and_its_disabled_colour(
    qapp: QApplication,
) -> None:
    """Draw the icon in the palette's button text colour, again after a change, and disabled in its own."""
    button = QPushButton()
    button.setPalette(palette("#ff0000", "#00ff00"))
    set_icon(button, "play", "Run the plan")
    first = colours(button.icon())

    button.setPalette(palette("#0000ff", "#00ff00"))
    QApplication.sendPostedEvents()

    assert "#ff0000" in first
    assert "#0000ff" in colours(button.icon())
    assert "#00ff00" in colours(button.icon(), QIcon.Mode.Disabled)


def test_a_collapsible_arrow_follows_the_palette(qapp: QApplication) -> None:
    """Draw a collapsible's arrows in its text colour, collapsed and expanded, again after a style sheet changes it."""
    collapsible = QCollapsible("Saved positions")
    collapsible.setStyleSheet("QPushButton { color: #ff0000; }")
    set_collapsible_icons(collapsible)
    first = colours(collapsible.toggleButton().icon())

    collapsible.setStyleSheet("QPushButton { color: #0000ff; }")
    QApplication.sendPostedEvents()
    collapsed = colours(collapsible.toggleButton().icon())
    collapsible.expand(animate=False)

    assert "#ff0000" in first
    assert "#0000ff" in collapsed
    assert "#0000ff" in colours(collapsible.toggleButton().icon())


def test_a_changed_icon_survives_a_palette_change(qapp: QApplication) -> None:
    """Keep the icon set last when the palette changes."""
    button = QPushButton()
    set_icon(button, "play", "Run the plan")
    set_icon(button, "stop", "Stop the plan")
    stopped = button.icon().pixmap(QSize(32, 32)).toImage()

    same = button.palette().color(QPalette.ColorRole.ButtonText).name()
    button.setPalette(palette(same, "#00ff00"))
    QApplication.sendPostedEvents()

    assert button.icon().pixmap(QSize(32, 32)).toImage() == stopped
    assert button.toolTip() == "Stop the plan"


def test_a_combo_item_gets_an_icon_and_keeps_its_text(qapp: QApplication) -> None:
    """Put an icon on a combo box item, keeping the item's text."""
    combo = QComboBox()
    combo.addItem("WARNING")

    set_item_icon(combo, 0, "alert")

    assert combo.itemText(0) == "WARNING"
    assert not combo.itemIcon(0).isNull()


def test_a_button_with_an_icon_is_freed_without_a_collection(
    qapp: QApplication,
) -> None:
    """Free a button given an icon as soon as nothing refers to it, with no collection."""
    gc.disable()
    try:
        button = QPushButton()
        set_icon(button, "play", "Run the plan")
        ref = weakref.ref(button)
        del button
        freed = ref() is None
    finally:
        gc.enable()

    assert freed


def test_an_icon_goes_on_its_own_button_not_a_child_with_one(
    qapp: QApplication,
) -> None:
    """Draw an icon on the button asked, even when a child button already has one."""
    outer = QPushButton()
    inner = QToolButton(outer)
    set_icon(inner, "stop", "Stop")

    set_icon(outer, "play", "Run the plan")

    assert not outer.icon().isNull()
    assert inner.toolTip() == "Stop"


@pytest.mark.skipif(
    "windows11" not in [name.lower() for name in STYLES],
    reason="the windows11 style is only built on Windows",
)
@pytest.mark.parametrize(
    ("accent", "expected"), [("#4cc2ff", "#000000"), ("#0067c0", "#ffffff")]
)
def test_a_checked_button_under_windows11_contrasts_with_its_accent(
    qapp: QApplication, accent: str, expected: str
) -> None:
    """Draw a checked button's icon black on a light accent and white on a dark one, under windows11."""
    button = QPushButton()
    button.setStyle(QStyleFactory.create("windows11"))
    shown = button.palette()
    shown.setColor(QPalette.ColorRole.Accent, QColor(accent))
    button.setPalette(shown)
    button.setCheckable(True)

    set_icon(button, "lightbulb-on", "Switch laser")

    image = button.icon().pixmap(QSize(32, 32), QIcon.Mode.Normal, QIcon.State.On)
    drawn = {
        image.toImage().pixelColor(x, y).name()
        for x in range(32)
        for y in range(32)
        if image.toImage().pixelColor(x, y).alpha() == 255
    }
    assert expected in drawn


def test_a_hovered_item_draws_its_icon_in_the_highlighted_text_colour(
    qapp: QApplication,
) -> None:
    """Draw a combo item's icon in the highlighted text colour when it is selected."""
    combo = QComboBox()
    shown = combo.palette()
    shown.setColor(QPalette.ColorRole.HighlightedText, QColor("#ff00ff"))
    combo.setPalette(shown)
    combo.addItem("WARNING")

    set_item_icon(combo, 0, "alert")

    assert "#ff00ff" in colours(combo.itemIcon(0), QIcon.Mode.Selected)


def test_an_application_palette_change_reaches_a_hidden_button(
    qapp: QApplication,
) -> None:
    """Redraw a hidden button's icon when the application palette changes, as a light/dark switch does."""
    button = QPushButton()
    set_icon(button, "play", "Run the plan")
    before = qapp.palette()
    try:
        qapp.setPalette(palette("#123456", "#654321"))
        QApplication.sendPostedEvents()
        drawn = colours(button.icon())
    finally:
        qapp.setPalette(before)

    assert "#123456" in drawn
