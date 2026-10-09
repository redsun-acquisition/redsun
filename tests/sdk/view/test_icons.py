"""Tests for the icons the built-in views draw from the icon font."""

from __future__ import annotations

import pytest
from qtpy.QtCore import QSize
from qtpy.QtGui import QColor, QIcon, QPalette
from qtpy.QtWidgets import QApplication, QComboBox, QPushButton

from redsun.view.qt._icons import set_icon, set_item_icon

pytestmark = pytest.mark.qt


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
