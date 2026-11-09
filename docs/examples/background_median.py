"""The session of the guide "How to run background processing"."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Any

import numpy as np
from event_model import DocumentRouter
from psygnal import Signal

from redsun import AsPresenter, Declare, ThreadExecutor, deliver, slot
from redsun.qt import QtSession

if TYPE_CHECKING:
    import numpy.typing as npt
    from event_model.documents import Event, RunStart, RunStop


# --8<-- [start:median]
def median_of(frames: list[npt.NDArray[Any]]) -> npt.NDArray[Any]:
    return np.asarray(np.median(np.stack(frames), axis=0))


# --8<-- [end:median]
# --8<-- [start:presenter]
class MedianPresenter(DocumentRouter):
    sig_median = Signal(object)

    def __init__(self, name: str, pool: ThreadExecutor, *, source: str) -> None:
        super().__init__()
        self.name = name
        self.source = source
        self._pool = pool
        self._frames: list[npt.NDArray[Any]] = []

    # --8<-- [start:documents]
    def start(self, doc: RunStart) -> RunStart:
        self._frames = []
        return doc

    def event(self, doc: Event) -> Event:
        self._frames.append(doc["data"][self.source])
        return doc

    def stop(self, doc: RunStop) -> RunStop:
        deliver(self._pool.submit(median_of, self._frames), self._publish)
        return doc

    def _publish(self, median: npt.NDArray[Any]) -> None:
        self.sig_median.emit(median)

    # --8<-- [end:documents]
    # --8<-- [start:recompute]
    @slot
    async def recompute(self) -> None:
        self.sig_median.emit(await self._pool.run(median_of, self._frames))

    # --8<-- [end:recompute]


# --8<-- [end:presenter]
# --8<-- [start:session]
class MyApp(QtSession):
    compute = "balanced"

    median: Annotated[AsPresenter[MedianPresenter], Declare(source="camera")]


if __name__ == "__main__":
    MyApp().run()
# --8<-- [end:session]
