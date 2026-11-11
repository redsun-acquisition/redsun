"""The session of the guide "How to run background processing"."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from event_model import DocumentRouter
from psygnal import Signal
from qtpy.QtWidgets import QLabel, QVBoxLayout, QWidget

from redsun import AsPresenter, AsView, Placement, slot
from redsun.compute import ThreadExecutor  # noqa: TC001
from redsun.log import Loggable
from redsun.qt import Dock, QtSession

if TYPE_CHECKING:
    from collections.abc import Iterator

    from event_model import Event, RunStart, RunStop
    from numpy.typing import NDArray

    from redsun import Link


# --8<-- [start:function]
def median_of(frames: list[NDArray[np.uint16]]) -> NDArray[np.float64]:
    return np.median(np.stack(frames), axis=0)


# --8<-- [end:function]
# --8<-- [start:presenter]
class MedianPresenter(DocumentRouter, Loggable):
    sig_median = Signal(object)

    def __init__(
        self, name: str, executor: ThreadExecutor, *, source: str = "camera"
    ) -> None:
        super().__init__()
        self.name = name
        self.source = source
        self._executor = executor
        self._frames: list[NDArray[np.uint16]] = []

    # --8<-- [end:presenter]
    # --8<-- [start:setup]
    def setup(self) -> None:
        blank = np.zeros((8, 8), dtype=np.uint16)
        self._executor.submit(median_of, [blank, blank]).then(self._warmed_up)

    def _warmed_up(self, median: NDArray[np.float64]) -> None:
        self.logger.info("Median ready")

    # --8<-- [end:setup]
    # --8<-- [start:documents]
    def start(self, doc: RunStart) -> RunStart:
        self._frames = []
        return doc

    def event(self, doc: Event) -> Event:
        self._frames.append(np.asarray(doc["data"][self.source]))
        return doc

    def stop(self, doc: RunStop) -> RunStop:
        if self._frames:
            future = self._executor.submit(median_of, self._frames)
            future.then(self.sig_median.emit, self._report)
        return doc

    def _report(self, error: BaseException) -> None:
        self.logger.warning(f"No median for this run: {error}")


# --8<-- [end:documents]
# --8<-- [start:view]
class MedianView(QWidget):
    placement: Placement = Dock("right")

    def __init__(self, name: str, parent: QWidget) -> None:
        super().__init__(parent)
        self.name = name
        self.label = QLabel("No median yet")
        QVBoxLayout(self).addWidget(self.label)

    @slot
    def show_median(self, median: NDArray[np.float64]) -> None:
        self.label.setText(f"Median ready, mean {median.mean():.1f}")


# --8<-- [end:view]
# --8<-- [start:session]
class MyApp(QtSession):
    median: AsPresenter[MedianPresenter]
    median_view: AsView[MedianView]

    def wire(self) -> Iterator[Link]:
        yield self.median.sig_median, self.median_view.show_median


if __name__ == "__main__":
    MyApp().run()
# --8<-- [end:session]
