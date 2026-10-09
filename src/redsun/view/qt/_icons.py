"""Icons the built-in views draw from the Material Design icon font."""

from __future__ import annotations

from typing import Final

from qtpy.QtCore import QEvent, QObject
from qtpy.QtGui import QIcon, QPalette
from qtpy.QtWidgets import QAbstractButton, QComboBox, QWidget
from superqt import fonticon

__all__ = ["set_icon", "set_item_icon"]

PREFIX: Final = "mdi7"
"""The icon font's prefix in `superqt.fonticon` keys."""


def icon(name: str, palette: QPalette) -> QIcon:
    """Return the icon *name* in *palette*'s button text colours, enabled and disabled."""
    # superqt keys its cache by the options, so the colours go in as names
    enabled = palette.color(QPalette.ColorRole.ButtonText).name()
    disabled = palette.color(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText
    ).name()
    return fonticon.icon(
        f"{PREFIX}.{name}", color=enabled, states={"disabled": {"color": disabled}}
    )


class Repaint(QObject):
    """Sets a widget's icons again when its palette changes.

    `superqt` draws an icon in the colour it was given and caches it, so a
    light/dark switch would leave the old colour.
    """

    def __init__(self, widget: QWidget) -> None:
        super().__init__(widget)
        self.widget = widget
        self.button: str | None = None
        self.items: dict[int, str] = {}
        widget.installEventFilter(self)

    def eventFilter(self, watched: QObject | None, event: QEvent | None) -> bool:
        """Draw the icons again on a palette change."""
        if event is not None and event.type() in (
            QEvent.Type.PaletteChange,
            QEvent.Type.ApplicationPaletteChange,
        ):
            self.draw()
        return False

    def draw(self) -> None:
        """Set every icon this widget shows, in its current palette."""
        palette = self.widget.palette()
        if self.button is not None and isinstance(self.widget, QAbstractButton):
            self.widget.setIcon(icon(self.button, palette))
        if isinstance(self.widget, QComboBox):
            for index, name in self.items.items():
                self.widget.setItemIcon(index, icon(name, palette))


def repaint_for(widget: QWidget) -> Repaint:
    """Return the widget's `Repaint`, made on first use."""
    found = widget.findChild(Repaint)
    return found if found is not None else Repaint(widget)


def set_icon(button: QAbstractButton, name: str, words: str) -> None:
    """Show the icon *name* on *button* in place of text, with *words* as tooltip and accessible name.

    The icon follows the button's palette from then on.
    """
    button.setText("")
    button.setToolTip(words)
    button.setAccessibleName(words)
    repaint = repaint_for(button)
    repaint.button = name
    repaint.draw()


def set_item_icon(combo: QComboBox, index: int, name: str) -> None:
    """Show the icon *name* beside item *index* of *combo*, following its palette."""
    repaint = repaint_for(combo)
    repaint.items[index] = name
    repaint.draw()
