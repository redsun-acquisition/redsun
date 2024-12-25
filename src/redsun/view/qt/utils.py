import threading
from typing import cast

from bluesky.utils import DuringTask
from qtpy.QtWidgets import QApplication


class ProcessEventsDuringTask(DuringTask):
    """Implementation of DuringTask that emits events to the Qt event loop."""

    def __init__(self) -> None:
        self.app = cast(QApplication, QApplication.instance())

    def block(self, blocking_event: threading.Event) -> None:
        """Keep processing events until the blocking event is out of the "waiting" state.

        In the default implementation, blocking_event.wait() prevents
        the Qt loop to correctly process events. They solve this
        by using a remote kicker that "kicks" the loop.

        This implementation simply calls processEvents() every 30ms.

        Parameters
        ----------
        blocking_event : asyncio.Event
            The event to wait for. This is provided by the Bluesky run engine.
        """
        while True:
            done = blocking_event.wait(timeout=0.03)
            self.app.processEvents()
            if done:
                break
