from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

    import culsans
    import numpy.typing as npt

__all__ = ["FrameSink"]


class FrameSink:
    """Producer-facing handle for one stream's frame queue.

    Exposes only the producer face of the underlying queue: the consumer
    face (``async_get``, immediate shutdown, ``clear``) stays private to
    the owning storage's drain task.

    Parameters
    ----------
    queue : culsans.Queue
        The bounded frame queue owned by the storage layer.
    """

    __slots__ = ("_queue",)

    def __init__(self, queue: culsans.Queue[npt.NDArray[Any]]) -> None:
        self._queue = queue

    async def put(self, frame: npt.NDArray[Any]) -> None:
        """Enqueue a frame from an async producer, parking when the queue is full.

        Raises
        ------
        culsans.QueueShutDown
            If the stream has reached capacity or was closed.
        """
        await self._queue.async_put(frame)

    def put_nowait(self, frame: npt.NDArray[Any]) -> None:
        """Enqueue a frame from a sync producer without ever blocking.

        Safe inside ``emit_sync`` document callbacks on the loop thread.

        Raises
        ------
        culsans.QueueFull
            If the queue is full — a callback bug or a stalled backend.
        culsans.QueueShutDown
            If the stream has reached capacity or was closed.
        """
        self._queue.green_put(frame, blocking=False)

    def close(self) -> None:
        """Shut the stream down cleanly. Idempotent.

        Queued frames are still written (flush semantics); further puts
        raise ``culsans.QueueShutDown``.
        """
        if not self._queue.is_shutdown:
            self._queue.shutdown()
