"""Python's garbage collection, moved onto the Qt GUI thread."""

# The approach, automatic collection off and a timer on the GUI thread doing
# its work, is the one pyqtgraph's GarbageCollector takes, which in turn
# credits a 2014 post by Erik Janssens; the code here is written separately.

from __future__ import annotations

import gc
from typing import Final

from qtpy.QtCore import QObject, QTimer

__all__ = ["GarbageCollector"]

INTERVAL: Final = 1000
"""Milliseconds between two checks of the collection counts."""


class GarbageCollector:
    """Collects Python's garbage from a timer on the GUI thread, never elsewhere.

    Python collects on whichever thread allocates when a count passes its
    threshold, and a widget destroyed off the GUI thread aborts the
    application under `pyside6`. While started, automatic collection is off
    and each check collects the oldest generation whose count passed its
    threshold, as automatic collection would.
    """

    __slots__ = ("__weakref__", "enabled_before", "timer")

    def __init__(self, parent: QObject) -> None:
        self.timer = QTimer(parent)
        self.timer.setInterval(INTERVAL)
        self.timer.timeout.connect(self.check)
        self.enabled_before = gc.isenabled()

    def start(self) -> None:
        """Turn automatic collection off and start checking."""
        self.enabled_before = gc.isenabled()
        gc.disable()
        self.timer.start()

    def stop(self) -> None:
        """Stop checking, and turn automatic collection back on if it was on."""
        self.timer.stop()
        if self.enabled_before:
            gc.enable()

    def check(self) -> None:
        """Collect the oldest generation whose count passed its threshold."""
        counts, thresholds = gc.get_count(), gc.get_threshold()
        due = [
            generation
            for generation in range(3)
            if counts[generation] > thresholds[generation]
        ]
        if due:
            gc.collect(max(due))
