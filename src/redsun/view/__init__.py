"""Where a view asks to be attached, where the session lays views out, and the widgets views share."""

from __future__ import annotations

from ._layout import Column, Row, Tabs, WindowLayout
from ._placement import Placement
from ._shortcut import Shortcut, shortcut

__all__ = ["Column", "Placement", "Row", "Shortcut", "Tabs", "WindowLayout", "shortcut"]
