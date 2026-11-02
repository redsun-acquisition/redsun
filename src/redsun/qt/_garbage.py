"""Python's garbage collection, moved onto the Qt GUI thread."""

# The approach, automatic collection off and a timer on the GUI thread doing
# its work, is the one pyqtgraph's GarbageCollector takes, which in turn
# credits a 2014 post by Erik Janssens; the code here is written separately.

from __future__ import annotations

import gc
import weakref
from typing import Final

from qtpy.QtCore import QObject, QTimer

__all__ = ["GarbageCollector"]

RUNNING: Final[weakref.WeakSet[GarbageCollector]] = weakref.WeakSet()
"""Collectors started and not stopped yet, which share automatic collection."""


class GarbageCollector:
    """Runs Python's automatic garbage collection from a timer on the GUI thread.

    Python collects on whichever thread allocates when a count passes its
    threshold, and a widget destroyed off the GUI thread aborts the
    application under `pyside6`. While started, automatic collection is off
    and each check collects the oldest generation whose count passed its
    threshold, as automatic collection would. A `gc.collect()` called on
    another thread still runs there.
    """

    __slots__ = ("__weakref__", "enabled_before", "timer")

    def __init__(self, parent: QObject, interval: int) -> None:
        """Check the collection counts every *interval* milliseconds once started."""
        self.timer = QTimer(parent)
        self.timer.setInterval(interval)
        self.timer.timeout.connect(self.check)
        self.enabled_before = gc.isenabled()

    def start(self) -> None:
        """Turn automatic collection off and start checking."""
        # a collector started while another runs finds automatic collection
        # off because of it, so it takes the state the first one found
        self.enabled_before = (
            next(iter(RUNNING)).enabled_before if RUNNING else gc.isenabled()
        )
        RUNNING.add(self)
        gc.disable()
        self.timer.start()

    def stop(self) -> None:
        """Stop checking for good, and turn automatic collection back on if it was on.

        Automatic collection stays off while another collector still runs.
        Before turning it on, collect once: this runs on the GUI thread, so
        the cycles left behind are freed there rather than by the next
        automatic collection on another thread. With automatic collection
        already off when the first running collector started, nothing is
        collected.
        """
        self.timer.stop()
        self.timer.deleteLater()
        RUNNING.discard(self)
        if self.enabled_before and not RUNNING:
            gc.collect()
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
