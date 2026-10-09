"""Icons the built-in views draw from the Material Design icon font."""

from __future__ import annotations

from typing import Final

from qtpy.QtCore import QEvent, QObject, QSize, Qt
from qtpy.QtGui import QIcon, QPalette
from qtpy.QtWidgets import QAbstractButton, QComboBox, QWidget
from superqt import QCollapsible, fonticon

__all__ = ["set_collapsible_icons", "set_icon", "set_item_icon"]

PREFIX: Final = "mdi7"
"""The icon font's prefix in `superqt.fonticon` keys."""

SCALE: Final = 1.4
"""An icon's size as a multiple of its widget's line height."""


def icon(name: str, widget: QWidget) -> QIcon:
    """Return the icon *name* in *widget*'s colours: enabled, disabled, checked and selected."""
    palette = widget.palette()
    # superqt keys its cache by the options, so the colours go in as names
    enabled = palette.color(QPalette.ColorRole.ButtonText).name()
    disabled = palette.color(
        QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText
    ).name()
    selected = palette.color(QPalette.ColorRole.HighlightedText).name()
    return fonticon.icon(
        f"{PREFIX}.{name}",
        color=enabled,
        states={
            "on": {"color": checked_colour(widget, enabled)},
            "disabled": {"color": disabled},
            "selected": {"color": selected},
        },
    )


def checked_colour(widget: QWidget, enabled: str) -> str:
    """Return the colour of a checked button's icon on *widget*'s style.

    The windows11 style fills a checked button with the accent colour and
    writes on it in black or white, whichever reads on that accent; no
    palette role holds that colour. Other styles keep the button text colour.
    """
    style = widget.style()
    if style is None or style.name().lower() != "windows11":
        return enabled
    accent = widget.palette().color(QPalette.ColorRole.Accent)
    return "#000000" if accent.lightnessF() > 0.5 else "#ffffff"


class Repaint(QObject):
    """Sets its parent widget's icons again when the widget's palette changes.

    `superqt` draws an icon in the colour it was given and caches it, so a
    light/dark switch would leave the old colour. The widget is read from
    the parent, not kept, so the two make no reference cycle.
    """

    def __init__(self, widget: QWidget) -> None:
        super().__init__(widget)
        self.button: str | None = None
        self.items: dict[int, str] = {}
        self.arrows: tuple[str, str] | None = None
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
        """Set every icon the parent widget shows, in its current palette."""
        widget = self.parent()
        if self.button is not None and isinstance(widget, QAbstractButton):
            widget.setIcon(icon(self.button, widget))
        if isinstance(widget, QComboBox):
            for index, name in self.items.items():
                widget.setItemIcon(index, icon(name, widget))
        if self.arrows is not None and isinstance(widget, QCollapsible):
            collapsed, expanded = self.arrows
            widget.setCollapsedIcon(icon(collapsed, widget.toggleButton()))
            widget.setExpandedIcon(icon(expanded, widget.toggleButton()))


def repaint_for(widget: QWidget) -> Repaint:
    """Return the widget's `Repaint`, made on first use."""
    found = widget.findChild(Repaint, options=Qt.FindChildOption.FindDirectChildrenOnly)
    return found if found is not None else Repaint(widget)


def set_icon(button: QAbstractButton, name: str, words: str) -> None:
    """Show the icon *name* on *button* in place of text, with *words* as tooltip and accessible name.

    The icon follows the button's palette from then on.
    """
    button.setText("")
    button.setToolTip(words)
    button.setAccessibleName(words)
    # the style's 16 px is smaller than the text an icon stands in for
    side = round(button.fontMetrics().height() * SCALE)
    button.setIconSize(QSize(side, side))
    repaint = repaint_for(button)
    repaint.button = name
    repaint.draw()


def set_item_icon(combo: QComboBox, index: int, name: str) -> None:
    """Show the icon *name* beside item *index* of *combo*, following its palette."""
    repaint = repaint_for(combo)
    repaint.items[index] = name
    repaint.draw()


def set_collapsible_icons(collapsible: QCollapsible) -> None:
    """Show *collapsible*'s arrows as icons following its palette.

    `QCollapsible` draws its own arrows once, in the text colour of that
    moment, so a light/dark switch would leave them in the old colour.
    """
    repaint = repaint_for(collapsible)
    repaint.arrows = ("menu-right", "menu-down")
    # the button has a style sheet of its own, so its palette changes apart
    # from the collapsible's and only the button's own events report it
    collapsible.toggleButton().installEventFilter(repaint)
    repaint.draw()
