from __future__ import annotations

from typing import TYPE_CHECKING

import culsans
import numpy as np
import pytest

from redsun.storage import FrameSink

if TYPE_CHECKING:
    from typing import Any

    import numpy.typing as npt


def frame(fill: int = 0) -> npt.NDArray[Any]:
    return np.full((4, 4), fill, dtype=np.uint16)


async def test_put_and_put_nowait_enqueue_frames() -> None:
    queue: culsans.Queue[npt.NDArray[Any]] = culsans.Queue(maxsize=4)
    sink = FrameSink(queue)
    await sink.put(frame(1))
    sink.put_nowait(frame(2))
    first = await queue.async_get()
    second = await queue.async_get()
    assert first[0, 0] == 1
    assert second[0, 0] == 2


async def test_put_nowait_full_queue_raises_loudly() -> None:
    queue: culsans.Queue[npt.NDArray[Any]] = culsans.Queue(maxsize=1)
    sink = FrameSink(queue)
    sink.put_nowait(frame())
    with pytest.raises(culsans.QueueFull):
        sink.put_nowait(frame())


async def test_close_is_idempotent_and_shuts_producers_out() -> None:
    queue: culsans.Queue[npt.NDArray[Any]] = culsans.Queue(maxsize=4)
    sink = FrameSink(queue)
    await sink.put(frame(7))
    sink.close()
    sink.close()  # idempotent - no raise
    with pytest.raises(culsans.QueueShutDown):
        sink.put_nowait(frame())
    with pytest.raises(culsans.QueueShutDown):
        await sink.put(frame())
    # queued frame is still consumable after clean shutdown (flush semantics)
    remaining = await queue.async_get()
    assert remaining[0, 0] == 7
